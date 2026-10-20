# celery/backends/base.py at 508c112 (#58): one task's errback failing is
# swallowed with no trace, and the loop goes on to the next task.
def fail_group_tasks(backend, frozen_group, group_callback, original_exc):
    for result in frozen_group.results:
        fake_request = make_request(
            task_id=result.id,
            errbacks=group_callback.options.get("link_error", []),
        )
        try:
            backend._call_task_errbacks(fake_request, original_exc, None)
        except Exception:  # pylint: disable=broad-except
            # continue on exception to be sure to iter to all the group tasks
            pass
        backend.fail_from_current_stack(result.id, exc=original_exc)
