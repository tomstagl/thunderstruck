# Configuration detector calibration

The configuration detectors added for #19 (AC-15) were swept with
`scripts/calibrate.py` over every tracked, non-excluded YAML and
`.properties` file of five public repositories. Each hit was read and judged
against the pattern's `failure_if_absent`, in the same way as the
[Java log](java.md). Every configuration detector ships at `confidence: low`.
Detectors with no hits here have not been measured on real code, and this
log says so rather than implying they were.

| Repo | Commit | Scope swept |
|---|---|---|
| GoogleCloudPlatform/microservices-demo | `38e7348eb289eb5b87c0c6e8cb19ced0449dc389` | whole tree |
| istio/istio | `4c255e181386ee39a2c2f3704f77e5d11afb7391` | `samples/` and `manifests/charts/` (sparse checkout) |
| spring-petclinic/spring-petclinic-microservices | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | whole tree |
| resilience4j/resilience4j-spring-boot3-demo | `6c3e644d53174182fb79c0e49770b191a1d7287c` | whole tree |
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | whole tree |

`.github/`, `docker-compose*.yml` and the other tooling configuration are
excluded by the shared filter (AC-12), so CI and local-dev files are not
swept.

| Detector | Hits | TP | FP-fixed | FP-accepted | FN-fixed | Final |
|---|---|---|---|---|---|---|
| S01-yaml-virtualservice-no-timeout | 27 | 25 | 0 | 2 | 0 | 27 |
| S10-yaml-mesh-retry | 0 | 0 | 0 | 0 | 0 | 0 |
| S10-yaml-resilience4j-retry | 0 | 0 | 0 | 0 | 1 | 1 |
| S10-properties-resilience4j-retry | 0 | 0 | 0 | 0 | 0 | 0 |
| S30-yaml-liveness-checks-dependencies | 0 | 0 | 0 | 0 | 0 | 0 |

The largest count in one repository is 22 (`S01-yaml-virtualservice-no-timeout`
in istio `samples/`), under the 25-hits-per-repo tripwire.

## Hits

### S01-yaml-virtualservice-no-timeout

Istio disables the HTTP route timeout by default, so an HTTP route with no
`timeout:` waits as long as the upstream does. That is the pattern.

- **microservices-demo**, 5 hits: `istio-manifests/frontend.yaml:16`,
  `istio-manifests/frontend-gateway.yaml:31`,
  `kustomize/components/service-mesh-istio/frontend.yaml:16`,
  `helm-chart/templates/frontend.yaml:267` and
  `release/istio-manifests.yaml:84`. All are **TP**: the frontend routes have
  no timeout. They are the same route written in four forms (plain manifest,
  kustomize component, Helm template, release bundle). The Helm template is
  scanned as text (spec §7.1), which is why it matches.
- **istio `samples/`**, 22 hits. 20 are **TP**: the bookinfo, helloworld,
  httpbin and cert-manager routes carry HTTP routes with no timeout. This
  includes the fault-injection demos
  (`virtual-service-ratings-test-delay.yaml`, `...-test-abort.yaml`), which
  inject delays into routes that have no timeout of their own. 2 are
  **FP-accepted**:
  - `samples/websockets/route.yaml:17` routes a WebSocket upgrade. A route
    timeout would cut long-lived connections, so leaving it unset is
    deliberate.
  - `samples/multicluster/expose-istiod-https.yaml:33` routes istiod's xDS
    ports 15012/15017, which carry long-lived gRPC streams, so a timeout is
    unwanted there too.

  Neither can be told apart from the route's text. Both are what
  `[[suppress]]` is for.

### S10-yaml-resilience4j-retry

- **FN-fixed**: `resilience4j-spring-boot3-demo`
  `src/main/resources/application.yml:67` (`maxAttempts: 3` under
  `resilience4j.retry:`). Spring Boot writes `resilience4j.retry:` as one
  dotted key, and the first `require` (`^\s*resilience4j:\s*$`) never
  matched it. `require` now also accepts `resilience4j.retry:`, and
  `S10/yaml/positive_dotted_keys.yaml` reproduces the shape. After the fix
  the hit is **TP**: a configured retry layer, which is what the inventory
  records.

## Not measured

`S10-yaml-mesh-retry`, `S10-properties-resilience4j-retry` and
`S30-yaml-liveness-checks-dependencies` had no hits on these repositories.
None of them defines mesh retries, resilience4j retries in `.properties`, or
a liveness probe on an aggregate health endpoint. spring-petclinic's probes
use `/livez` and `/readyz`, which S30 correctly leaves alone. Their samples
prove the regexes do what they were written for; they do not show behaviour
on code nobody wrote for the test. They stay `low` until a sweep finds hits
to judge.
