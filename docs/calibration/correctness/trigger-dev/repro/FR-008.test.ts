// FR-008 reproduction (labelling, not part of the upstream suite).
// run: cd internal-packages/clickhouse && pnpm run test src/FR-008.test.ts --run --reporter=verbose
//
// Claim: span detail fails when a stored attributes_text is not valid JSON, because
// #parseAttributes is a bare JSON.parse (clickhouseEventRepository.server.ts:2700-2706).
// Question: can the write path store attributes_text that JSON.parse rejects?
// attributes_text is a plain String filled by the writer with JSON.stringify
// (serializeTaskEventAttributes, src/taskEvents.ts:233-239); the inserter disables
// input_format_json_throw_on_bad_escape_sequence. We push hostile attribute values through
// the real writer into a real ClickHouse and JSON.parse what comes back.
import { clickhouseTest } from "@internal/testcontainers";
import { z } from "zod";
import { ClickHouse } from "./index.js";

const d = (v: Date) => v.toISOString().replace("T", " ").replace("Z", "");

const hostile: Record<string, unknown> = {
  loneHigh: "a\ud800b",
  loneLow: "a\udc00b",
  reversedPair: "\udc00\ud800",
  backslashU: "\\u12",
  backslashX: '{"a":"\\x"}',
  rawBackslashes: "C:\\path\\to\\nowhere\\",
  controls: "\u0000\u0001\u001f\u007f",
  quotes: '"\'`',
  emoji: "😀",
  big: "x".repeat(200_000),
  nested: { deep: [1, "\ud83d", { k: "\\" }] },
  "key\ud800": "lone surrogate in a key",
};

describe("FR-008", () => {
  clickhouseTest(
    "attributes_text written by the writer always parses",
    async ({ clickhouseContainer }) => {
      const ch = new ClickHouse({ url: clickhouseContainer.getConnectionUrl(), name: "fr008" });
      const entries = Object.entries(hostile);
      const [insertError] = await ch.taskEventsV2.insert(
        entries.map(([k, v], i) => ({
          environment_id: "env_fr008",
          organization_id: "org_fr008",
          project_id: "proj_fr008",
          task_identifier: "fr008",
          run_id: "run_fr008",
          start_time: d(new Date("2026-09-01T10:00:00.000Z")),
          duration: "1000",
          trace_id: "trace_fr008",
          span_id: `span_${i}`,
          parent_span_id: "",
          message: `case ${k}`,
          kind: "SPAN",
          status: "OK",
          metadata: "{}",
          expires_at: d(new Date(Date.now() + 86_400_000)),
          attributes: { [k]: v },
        }))
      );
      expect(insertError).toBeNull();

      const [readError, rows] = await ch.reader.query({
        name: "fr008-read",
        query:
          "SELECT span_id, attributes_text FROM trigger_dev.task_events_v2 WHERE environment_id = 'env_fr008' ORDER BY span_id",
        schema: z.object({ span_id: z.string(), attributes_text: z.string() }),
      })({});
      expect(readError).toBeNull();
      expect(rows.length).toBe(entries.length);

      const failures: string[] = [];
      for (const row of rows) {
        try {
          JSON.parse(row.attributes_text);
        } catch (e) {
          failures.push(`${row.span_id}: ${(e as Error).message} :: ${row.attributes_text.slice(0, 80)}`);
        }
      }
      console.log(`FR-008 rows=${rows.length} parseFailures=${failures.length} ${JSON.stringify(failures)}`);
      expect(failures).toEqual([]);

      // The finding's own example, if it were stored, would throw:
      expect(() => JSON.parse('{"a":"\\x"}')).toThrow();
    }
  );
});
