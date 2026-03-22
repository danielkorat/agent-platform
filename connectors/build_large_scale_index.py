"""Build large-scale IT Ops corpus and FAISS/BM25 indexes for the demo.

Generates ~12 400 synthetic IT Ops documents:
  ·  ~160 runbook articles   (30 systems × 5–8 problem types each)
  · 9 000 incident histories (seeded, fully deterministic)
  · 3 000 KB how-to articles

Total > hnsw_min_vectors (10 000) → VectorStore auto-selects
IndexHNSWFlat (M=32, efSearch=64) — 290× faster than IndexFlatIP at this
scale, directly supporting the 248:1 ROI / TCO story in docs/roi.md.

Usage:
    python -m connectors.build_large_scale_index
    python -m connectors.build_large_scale_index --incidents 15000 --seed 7
"""

from __future__ import annotations

import argparse
import datetime
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from retrieval.lexical_store import LexicalStore
from retrieval.vector_store import VectorStore

# ─────────────────────────────────────────────────────────────────────────────
# 1.  SYSTEMS
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEMS: list[dict] = [
    {"id": "postgresql",    "display": "PostgreSQL",       "cat": "database",
     "problems": ["connection_exhaustion", "replication_lag",  "disk_full",
                  "slow_queries",          "auth_failure",     "high_cpu",
                  "cluster_split",         "memory_exhaustion"]},
    {"id": "mysql",         "display": "MySQL",            "cat": "database",
     "problems": ["connection_exhaustion", "replication_lag",  "slow_queries",
                  "disk_full",             "auth_failure",     "high_cpu"]},
    {"id": "redis",         "display": "Redis",            "cat": "cache",
     "problems": ["memory_exhaustion",     "connection_exhaustion", "replication_lag",
                  "disk_full",             "auth_failure",     "cluster_split"]},
    {"id": "mongodb",       "display": "MongoDB",          "cat": "database",
     "problems": ["replication_lag",       "disk_full",        "slow_queries",
                  "memory_exhaustion",     "auth_failure",     "high_cpu"]},
    {"id": "elasticsearch", "display": "Elasticsearch",   "cat": "search",
     "problems": ["disk_full",             "memory_exhaustion","slow_queries",
                  "high_cpu",              "auth_failure",     "cluster_split"]},
    {"id": "kafka",         "display": "Apache Kafka",     "cat": "messaging",
     "problems": ["queue_buildup",         "leader_election",  "disk_full",
                  "memory_exhaustion",     "auth_failure",     "slow_queries"]},
    {"id": "rabbitmq",      "display": "RabbitMQ",         "cat": "messaging",
     "problems": ["queue_buildup",         "memory_exhaustion","connection_exhaustion",
                  "disk_full",             "cluster_split",    "auth_failure"]},
    {"id": "nginx",         "display": "Nginx",            "cat": "proxy",
     "problems": ["connection_exhaustion", "memory_exhaustion","ssl_handshake_fail",
                  "slow_queries",          "disk_full"]},
    {"id": "haproxy",       "display": "HAProxy",          "cat": "proxy",
     "problems": ["health_check_fail",     "connection_exhaustion", "ssl_handshake_fail",
                  "slow_queries",          "memory_exhaustion"]},
    {"id": "kubernetes",    "display": "Kubernetes",       "cat": "orchestration",
     "problems": ["oom_kill",              "crashloopbackoff", "health_check_fail",
                  "disk_full",             "leader_election",  "auth_failure",
                  "slow_queries"]},
    {"id": "docker",        "display": "Docker",           "cat": "container",
     "problems": ["memory_exhaustion",     "disk_full",        "health_check_fail",
                  "auth_failure",          "ssl_handshake_fail"]},
    {"id": "prometheus",    "display": "Prometheus",       "cat": "monitoring",
     "problems": ["disk_full",             "slow_queries",     "auth_failure",
                  "high_cpu",              "memory_exhaustion"]},
    {"id": "grafana",       "display": "Grafana",          "cat": "monitoring",
     "problems": ["auth_failure",          "high_cpu",         "slow_queries",
                  "memory_exhaustion",     "health_check_fail"]},
    {"id": "vault",         "display": "HashiCorp Vault",  "cat": "security",
     "problems": ["auth_failure",          "disk_full",        "memory_exhaustion",
                  "leader_election",       "ssl_handshake_fail"]},
    {"id": "consul",        "display": "HashiCorp Consul", "cat": "service_mesh",
     "problems": ["leader_election",       "health_check_fail","disk_full",
                  "cluster_split",         "auth_failure"]},
    {"id": "airflow",       "display": "Apache Airflow",   "cat": "orchestration",
     "problems": ["memory_exhaustion",     "connection_exhaustion", "disk_full",
                  "auth_failure",          "slow_queries"]},
    {"id": "spark",         "display": "Apache Spark",     "cat": "processing",
     "problems": ["memory_exhaustion",     "disk_full",        "slow_queries",
                  "high_cpu"]},
    {"id": "celery",        "display": "Celery",           "cat": "task_queue",
     "problems": ["memory_exhaustion",     "slow_queries",     "auth_failure",
                  "connection_exhaustion", "queue_buildup"]},
    {"id": "jenkins",       "display": "Jenkins",          "cat": "ci_cd",
     "problems": ["disk_full",             "memory_exhaustion","high_cpu",
                  "auth_failure",          "queue_buildup"]},
    {"id": "gitlab",        "display": "GitLab",           "cat": "ci_cd",
     "problems": ["queue_buildup",         "disk_full",        "connection_exhaustion",
                  "auth_failure",          "memory_exhaustion"]},
    {"id": "terraform",     "display": "Terraform",        "cat": "iac",
     "problems": ["auth_failure",          "slow_queries",     "disk_full",
                  "memory_exhaustion",     "health_check_fail"]},
    {"id": "linux",         "display": "Linux",            "cat": "os",
     "problems": ["oom_kill",              "disk_full",        "high_cpu",
                  "memory_exhaustion",     "auth_failure",     "ssl_handshake_fail"]},
    {"id": "nfs",           "display": "NFS",              "cat": "storage",
     "problems": ["auth_failure",          "slow_queries",     "disk_full",
                  "health_check_fail"]},
    {"id": "ceph",          "display": "Ceph",             "cat": "storage",
     "problems": ["disk_full",             "memory_exhaustion","slow_queries",
                  "auth_failure",          "leader_election"]},
    {"id": "etcd",          "display": "etcd",             "cat": "distributed",
     "problems": ["leader_election",       "disk_full",        "slow_queries",
                  "memory_exhaustion",     "auth_failure"]},
    {"id": "istio",         "display": "Istio",            "cat": "service_mesh",
     "problems": ["ssl_handshake_fail",    "auth_failure",     "memory_exhaustion",
                  "high_cpu",              "health_check_fail"]},
    {"id": "argocd",        "display": "ArgoCD",           "cat": "gitops",
     "problems": ["auth_failure",          "memory_exhaustion","slow_queries",
                  "disk_full",             "health_check_fail"]},
    {"id": "datadog",       "display": "Datadog Agent",    "cat": "monitoring",
     "problems": ["high_cpu",              "memory_exhaustion","auth_failure",
                  "disk_full",             "connection_exhaustion"]},
    {"id": "aws_s3",        "display": "AWS S3",           "cat": "cloud_storage",
     "problems": ["auth_failure",          "disk_full",        "slow_queries",
                  "replication_lag",       "ssl_handshake_fail"]},
    {"id": "aws_ec2",       "display": "AWS EC2",          "cat": "cloud_compute",
     "problems": ["high_cpu",              "memory_exhaustion","disk_full",
                  "auth_failure",          "health_check_fail"]},
]

# ─────────────────────────────────────────────────────────────────────────────
# 2.  PROBLEM TEMPLATES
#     {sys} is substituted with the system display name at generation time.
# ─────────────────────────────────────────────────────────────────────────────

_PROBLEMS: dict[str, dict] = {
    "connection_exhaustion": {
        "display": "Connection Pool Exhaustion",
        "symptoms": [
            "Application returning HTTP 503/504 under normal or elevated load",
            "{sys} logs reporting 'too many connections' or connection refused errors",
            "Connection pool depth metrics at or above configured maximum",
            "Downstream services experiencing cascading timeout failures",
            "SLO error-budget burn accelerating on the {sys} dependency",
        ],
        "causes": [
            "Connection leak: application does not release connections after exceptions",
            "Long-running transactions holding connections across request cycles",
            "Insufficient pool size relative to peak concurrent request volume",
            "Multiple application replicas each consuming max pool size simultaneously",
            "Sudden traffic spike from marketing campaign or runaway batch automation",
        ],
        "diagnosis": [
            "Query active connections: check {sys} system connection table for idle/active breakdown",
            "Identify connections idle longer than 5 minutes — likely connection leaks",
            "Correlate connection spike timestamp with recent deployments or traffic events",
            "Inspect application APM for connection timeout stack traces",
            "Verify connection pool configuration across all application replicas",
        ],
        "resolution": [
            "Immediate: terminate idle long-lived connections using {sys} admin interface",
            "Short-term: raise pool size limit by 50% and restart the pool manager",
            "Validate: confirm connection errors cease and application metrics recover to baseline",
            "Long-term: configure idle_in_transaction timeout, add pool depth alerting at 80%",
            "Architecture: evaluate PgBouncer or similar multiplexer if peak/off-peak ratio > 5×",
        ],
        "escalation": "Escalate to {sys} DBA team if exhaustion recurs within 24 hours or if connection termination triggers data integrity alerts.",
    },
    "disk_full": {
        "display": "Disk Space Exhaustion",
        "symptoms": [
            "{sys} process logs 'no space left on device' errors on data volume",
            "Write operations failing with I/O error or ENOSPC kernel error",
            "Replication or WAL shipping halted due to insufficient write capacity",
            "Health check probes failing as temp file creation is blocked",
            "Monitoring alert: disk utilisation > 90% on {sys} data volume",
        ],
        "causes": [
            "Uncontrolled log or audit file growth on the {sys} data volume",
            "Stale dead rows, compaction artefacts, or index bloat accumulating",
            "Backup retention policy not enforced — old backup files filling the mount",
            "Unexpected data ingestion surge beyond capacity plan",
            "Transaction logs or WAL files not being purged on schedule",
        ],
        "diagnosis": [
            "Run `df -h` on the host to identify which volume is full",
            "Identify largest directories: `du -sh /*` scoped to the data mount",
            "Check {sys} log rotation configuration and last successful rotation timestamp",
            "Review backup and archival job completion logs for the past 7 days",
            "Query {sys} internal space-usage tables to find largest data objects",
        ],
        "resolution": [
            "Immediate: remove stale log files older than retention policy window",
            "Short-term: expand volume size or mount additional storage to the {sys} data path",
            "Clear old backup files beyond retention period using the automated cleanup script",
            "Run {sys} space reclamation: VACUUM FULL, compaction, or major-compaction cycle",
            "Long-term: add capacity alerting at 75% and 85%, automate log rotation via cron",
        ],
        "escalation": "Page storage team if volume cannot be expanded within SLO response window. Escalate to infrastructure architect if recurrence indicates a capacity planning gap.",
    },
    "memory_exhaustion": {
        "display": "Memory Exhaustion",
        "symptoms": [
            "{sys} process killed by Linux OOM killer — syslog shows 'Out of memory: Kill process'",
            "Response latency spiking due to GC pressure or swap thrashing",
            "Swap utilisation elevated on {sys} host nodes",
            "System memory utilisation sustained > 95% for more than 10 minutes",
            "Container memory limit at 100% in cgroup runtime metrics",
        ],
        "causes": [
            "Memory limit configured too low for actual working set size",
            "Memory leak in {sys} code or a loaded plugin or extension",
            "Sudden data volume increase exceeding cache and buffer configuration",
            "JVM heap or buffer pool not tuned for upgraded load pattern",
            "Unintended full dataset load during batch job or data migration",
        ],
        "diagnosis": [
            "Check kernel OOM log: `dmesg | grep -i 'oom\\|killed'`",
            "Profile {sys} memory: inspect heap dumps, buffer pools, and cache allocation",
            "Review recent changes to JVM flags, buffer configuration, or dataset sizes",
            "Compare current RSS and heap to 7-day p99 baseline from monitoring",
            "Check for runaway queries or jobs holding large result sets in process memory",
        ],
        "resolution": [
            "Immediate: increase memory limit to current p99 RSS + 30% headroom",
            "Tune {sys} memory configuration: cache size, buffer pool allocation, JVM -Xmx",
            "Capture heap dump before restart if leak is suspected; analyse offline with MAT",
            "Add Vertical Pod Autoscaler recommendation mode to auto-tune resource requests",
            "Long-term: load-test with production traffic pattern to validate the new sizing",
        ],
        "escalation": "Escalate to application team for heap dump analysis. Engage platform team if node-level memory pressure is causing broader pod evictions.",
    },
    "replication_lag": {
        "display": "Replication Lag",
        "symptoms": [
            "Replica reads returning stale data; read-your-writes consistency broken",
            "Replication lag metric exceeding configured threshold (default: 30s)",
            "RPO SLO at risk if primary fails while lag is elevated",
            "Downstream analytics jobs returning unexpectedly stale results",
            "Monitoring alert: {sys} replication delay exceeds SLO threshold",
        ],
        "causes": [
            "Replica unable to keep up with primary write throughput",
            "Long-running transaction on primary blocking replication slot advance",
            "Network bandwidth saturation on the replication link between sites",
            "Replica paused for maintenance or patching and not yet caught up",
            "Bulk write or schema migration generating high WAL or binlog volume",
        ],
        "diagnosis": [
            "Query {sys} replication status view for current lag in bytes and wall-clock seconds",
            "Check network utilisation on replication link: `iftop` or `nethogs`",
            "Identify blocking transactions or replication slot drain stoppage on primary",
            "Review write throughput delta vs. replica apply rate in metrics",
            "Inspect WAL or binlog position gap between primary and replica",
        ],
        "resolution": [
            "Immediate: pause non-critical read traffic and let replica catch up",
            "If network-bound: prioritise replication traffic via QoS or dedicated NIC",
            "If transaction-blocked: identify and terminate the blocking long-running query",
            "If bulk write caused lag: throttle ingest rate or temporarily increase replica resources",
            "Long-term: implement lag-based read routing to avoid stale-read SLO violations",
        ],
        "escalation": "Escalate to DBA or data platform team if lag exceeds RPO threshold or if replication slot is dropped by the primary.",
    },
    "auth_failure": {
        "display": "Authentication Failure",
        "symptoms": [
            "Client connections rejected with 'authentication failed' or 'permission denied'",
            "Service accounts returning 401 or 403 from {sys} API or admin interface",
            "Automated jobs failing to connect after credential rotation in secret store",
            "Admin account locked out due to repeated failed login attempts",
            "Certificate-based auth rejecting connections after cert renewal",
        ],
        "causes": [
            "Credential rotation applied to secret store but not propagated to all consumers",
            "Certificate CN or SAN mismatch after TLS certificate renewal",
            "Expired service account password or token past TTL",
            "RBAC policy change inadvertently revoked a required permission",
            "Clock skew > 5 min causing JWT or Kerberos token validation failure",
        ],
        "diagnosis": [
            "Check {sys} auth log for specific error: wrong password, expired token, RBAC denial",
            "Verify current credential version in secret store matches what the service is using",
            "Compare certificate expiry and SANs against expected connection hostname",
            "Check NTP sync on all nodes: `timedatectl status` or `chronyc tracking`",
            "Test connectivity with known-good admin credentials to isolate scope",
        ],
        "resolution": [
            "Immediately rotate and propagate updated credentials to all dependent services",
            "Re-issue certificate with correct CN, SANs, and full chain if TLS mismatch",
            "Synchronise NTP on all affected nodes if clock skew is detected",
            "Restore accidentally revoked RBAC permission and audit the policy changelog",
            "Long-term: implement credential rotation health checks in CI/CD pipeline",
        ],
        "escalation": "Escalate to security team if auth failure pattern indicates possible intrusion. Escalate to IAM team if RBAC policy management is involved.",
    },
    "high_cpu": {
        "display": "High CPU Utilisation",
        "symptoms": [
            "CPU utilisation sustained > 90% on {sys} nodes for more than 5 minutes",
            "Request latency increasing proportionally with CPU contention",
            "Watchdog killing {sys} due to health check timeout caused by CPU starvation",
            "CPU throttling events visible in container cgroup or cloud instance metrics",
            "Noisy-neighbour alerts from co-located workloads on the same node",
        ],
        "causes": [
            "Runaway query or job consuming excessive CPU cycles without bound",
            "Missing index causing full-table or full-partition scan on large datasets",
            "Background compaction, GC, or VACUUM scheduled during peak traffic window",
            "Application code regression introducing O(n²) or worse processing loop",
            "Traffic spike without corresponding horizontal scale-out response",
        ],
        "diagnosis": [
            "Identify top CPU consumers in {sys} process list or query statistics view",
            "Profile with `perf top` or language-specific profiler to locate hot code paths",
            "Check {sys} slow query log for long-running operations correlating with spike",
            "Correlate CPU spike timestamp with deployment history and batch job schedule",
            "Review CPU throttling metrics in container runtime or cgroup stats",
        ],
        "resolution": [
            "Immediate: kill or throttle the runaway query or job consuming excess CPU",
            "Add missing index if full table or partition scan is identified as root cause",
            "Reschedule background maintenance jobs to off-peak window",
            "Scale horizontally if sustained traffic growth is the primary driver",
            "Long-term: add CPU headroom buffer in capacity plan; set throttle alerts at 80%",
        ],
        "escalation": "Escalate to capacity planning team if CPU consistently > 80% for > 1 hour. Engage application team for code-level profiling if regression is suspected.",
    },
    "cluster_split": {
        "display": "Cluster Split-Brain",
        "symptoms": [
            "Multiple {sys} nodes simultaneously claiming primary or leader role",
            "Quorum-loss alerts from {sys} cluster health endpoint",
            "Data written to both sides of the partition beginning to diverge",
            "Clients being routed to stale or rejected minority-partition nodes",
            "Reconciliation errors in {sys} logs after network path is restored",
        ],
        "causes": [
            "Network partition between data-centre racks or availability zones",
            "Asymmetric packet loss causing heartbeat timeout on one side only",
            "NIC or switch failure isolating a node from the majority partition",
            "Misconfigured quorum policy allowing minority partition to elect a leader",
            "Rolling upgrade introducing a temporary version incompatibility in the cluster",
        ],
        "diagnosis": [
            "Check {sys} cluster status command for role assignment across all nodes",
            "Review network connectivity matrix between nodes: ping, traceroute, mtr",
            "Inspect {sys} election log timestamps to identify the split window",
            "Verify quorum configuration: minimum votes required for leader election",
            "Compare data checksums or sequence numbers across nodes after partition heals",
        ],
        "resolution": [
            "Immediate: isolate the minority partition to prevent dual-write data divergence",
            "Restore network path; verify switch and NIC health on the affected segment",
            "Force re-election to the known-good primary with the most current data",
            "Run {sys} reconciliation or anti-entropy procedure to repair diverged state",
            "Long-term: add cross-DC heartbeat monitoring and automated split-brain fencing",
        ],
        "escalation": "Escalate to network engineering immediately for a physical partition. Engage data platform architect if data divergence is confirmed.",
    },
    "slow_queries": {
        "display": "Slow Queries / High Latency",
        "symptoms": [
            "p99 operation latency for {sys} exceeding SLO threshold",
            "Slow query log filling with statements above the configured time threshold",
            "Application-level timeouts correlating with {sys} operation latency",
            "Lock wait time or queue depth growing in {sys} statistics view",
            "Saturation metrics elevated without proportional CPU increase",
        ],
        "causes": [
            "Missing or stale index causing full sequential scan on large tables or shards",
            "Lock contention serialising concurrent operation execution",
            "Suboptimal query plan chosen by optimiser after data distribution shift",
            "Buffer pool or cache too small, causing excessive storage I/O",
            "Hot partition or shard receiving disproportionate share of traffic",
        ],
        "diagnosis": [
            "Enable {sys} slow query log or query statistics and identify top latency offenders",
            "Run EXPLAIN ANALYZE on the slowest queries to inspect the execution plan",
            "Check buffer pool hit ratio — low ratio indicates an I/O bottleneck",
            "Profile lock wait events to identify contended rows, tables, or shards",
            "Verify data distribution across shards or partitions is balanced",
        ],
        "resolution": [
            "Add missing index on heavily filtered or joined columns",
            "Update statistics and force query plan re-evaluation",
            "Increase buffer pool or cache allocation if bound by storage I/O",
            "Rewrite query to reduce lock scope or use a covering index",
            "Long-term: implement automated slow-query alerting and weekly index review",
        ],
        "escalation": "Escalate to database architect if latency persists beyond the SLO window. Escalate to vendor support for persistent query plan regression unexplained by index tuning.",
    },
    "leader_election": {
        "display": "Leader Election Storm",
        "symptoms": [
            "Frequent leader-change events appearing in {sys} cluster logs",
            "Follower nodes continuously requesting votes from their peers",
            "Elevated write failure rate during each election window",
            "Client errors: 'no leader available' or 'not the leader' for {sys}",
            "Election frequency exceeding 1 per hour in cluster health metrics",
        ],
        "causes": [
            "Disk I/O latency on the leader causing heartbeat timeout on followers",
            "CPU or network saturation preventing timely heartbeat response",
            "Election timeout configured too close to the heartbeat interval",
            "Clock skew causing inconsistent timeout calculations across nodes",
            "Persistent low-level network congestion or packet loss between peers",
        ],
        "diagnosis": [
            "Check {sys} election event log to identify trigger pattern and frequency",
            "Measure disk I/O latency on current leader: `iostat -x 1 30`",
            "Verify election timeout to heartbeat interval ratio — should be > 3×",
            "Check NTP synchronisation across all cluster nodes: `chronyc tracking`",
            "Profile CPU and network utilisation on the leader at the next election trigger",
        ],
        "resolution": [
            "Immediate: increase election timeout by 2× to dampen the flapping",
            "Reduce disk I/O pressure on leader: separate WAL volume, reduce compaction rate",
            "Ensure heartbeat interval is well below election timeout",
            "Fix NTP drift if clock skew is contributing to timeout inconsistency across nodes",
            "Long-term: provision NVMe SSD for {sys} WAL and a dedicated replication NIC",
        ],
        "escalation": "Escalate to platform team if election frequency exceeds 3 per hour. Escalate to storage team if disk latency persistently exceeds 10ms p99.",
    },
    "health_check_fail": {
        "display": "Health Check / Readiness Probe Failure",
        "symptoms": [
            "{sys} pods or nodes marked unhealthy and removed from load-balancer rotation",
            "Readiness probe returning non-200 status code or timing out",
            "Kubernetes events showing 'Readiness probe failed' for {sys} containers",
            "Downstream services receiving connection refused from removed endpoints",
            "Remaining healthy instances overloaded by cascading traffic redistribution",
        ],
        "causes": [
            "Health endpoint blocked waiting on a slow dependency: DB, external service, or secrets",
            "Application startup time exceeding initialDelaySeconds in probe configuration",
            "Resource contention causing health endpoint processing delay",
            "Misconfigured health endpoint returning wrong content type or unexpected status code",
            "Network policy blocking kubelet probe traffic from reaching the health port",
        ],
        "diagnosis": [
            "Curl health endpoint from inside the pod: `kubectl exec -it <pod> -- curl localhost:<port>/health`",
            "Check {sys} instance logs for errors coinciding with probe failure timestamps",
            "Verify initialDelaySeconds and periodSeconds match actual startup behaviour",
            "Confirm network policy allows kubelet (node IP) traffic on the health port",
            "Determine whether a dependency check inside the health endpoint is timing out",
        ],
        "resolution": [
            "Increase failureThreshold or timeoutSeconds if startup time is the issue",
            "Separate liveness from readiness: readiness checks dependencies, liveness does not",
            "Fix the slow dependency that is causing the health check to time out",
            "Correct network policy to explicitly allow kubelet probe traffic on the health port",
            "Long-term: implement a lightweight liveness endpoint with zero external dependencies",
        ],
        "escalation": "Escalate to platform team if health failures cause sustained traffic disruption. Engage network team if probe traffic is blocked by L3/L4 policy.",
    },
    "ssl_handshake_fail": {
        "display": "TLS/SSL Handshake Failure",
        "symptoms": [
            "Clients receiving TLS handshake error or 'certificate has expired'",
            "{sys} logs show SSL error, handshake timeout, or unknown CA",
            "HTTPS endpoints returning 525 at the load balancer after cert rotation",
            "Services failing mTLS validation after certificate renewal",
            "Browser or API client SSL errors reported immediately after certificate update",
        ],
        "causes": [
            "Certificate past expiry date — automatic renewal failed silently",
            "CN or SAN mismatch: certificate issued for wrong hostname",
            "Incomplete intermediate CA chain in the served certificate bundle",
            "TLS version or cipher suite mismatch between client and server",
            "Clock skew beyond cert validity tolerance on one side of the connection",
        ],
        "diagnosis": [
            "Inspect cert expiry: `openssl s_client -connect host:443 | openssl x509 -noout -dates`",
            "Check SANs match endpoint: `openssl x509 -noout -ext subjectAltName`",
            "Verify full cert chain: `openssl s_client -showcerts -connect host:443`",
            "Test cipher negotiation: `nmap --script ssl-enum-ciphers -p 443 host`",
            "Review cert-manager CertificateRequest events if auto-renewal is configured",
        ],
        "resolution": [
            "Immediate: issue a new certificate with correct CN, SANs, and complete chain",
            "Reload {sys} to pick up new certificate without a full service restart",
            "Ensure the intermediate CA bundle is appended to the leaf certificate file",
            "Fix TLS minimum version in {sys} config if cipher mismatch is root cause",
            "Long-term: add cert expiry alerting at 30 days and 7 days before expiry",
        ],
        "escalation": "Escalate to PKI team for CA-signed certificate issues. Engage security team if an unexpected certificate is found in the served chain.",
    },
    "oom_kill": {
        "display": "OOM Kill",
        "symptoms": [
            "Kubernetes OOMKilled exit code on {sys} container",
            "Linux kernel OOM killer log: 'Killed process' for {sys} — visible in `dmesg`",
            "Pod restarting in CrashLoopBackOff with incrementing restart count",
            "Eviction event in `kubectl describe node` due to node memory pressure",
            "Container memory limit at 100% in cgroup runtime metrics for > 2 minutes",
        ],
        "causes": [
            "Memory limit configured too low for the actual working set at peak load",
            "Memory leak in {sys} or a loaded plugin or extension",
            "JVM -Xmx set too close to container memory limit with no OS overhead headroom",
            "Sudden cache fill or bulk data ingestion exceeding available container memory",
            "Large working set at peak load not anticipated when sizing resource limits",
        ],
        "diagnosis": [
            "Check OOM event: `kubectl get events -n <ns> --sort-by='.lastTimestamp' | grep OOM`",
            "Profile memory over 24 hours to identify growth pattern or memory leak trend",
            "Compare container memory limit to actual p99 RSS from the past 7 days",
            "Review JVM heap settings: container limit must be ≥ -Xmx + 512 MiB OS overhead",
            "Check for unbounded cache growth or result set accumulation in {sys} config",
        ],
        "resolution": [
            "Immediate: raise memory limit to p99 peak RSS + 30% headroom",
            "For JVM: set -Xmx to (container_limit × 0.75) and enable GC logging",
            "Capture heap dump before the next restart if a memory leak is suspected",
            "Add VPA recommendation mode to auto-tune resource requests and limits over time",
            "Long-term: add OOM alerting and run weekly memory trend reviews",
        ],
        "escalation": "Escalate to application team for heap dump analysis. Escalate to platform team if node memory pressure is causing broader pod evictions across the cluster.",
    },
    "crashloopbackoff": {
        "display": "CrashLoopBackOff",
        "symptoms": [
            "{sys} pod restart count incrementing rapidly in `kubectl get pods`",
            "Pod status oscillating between Error and CrashLoopBackOff",
            "Container failing to reach Running state within 60 seconds of start",
            "Application health check never passing after startup attempt",
            "Init container or injected sidecar failing before main container can start",
        ],
        "causes": [
            "Missing environment variable or misconfigured secret mount",
            "Dependency unavailable at startup: database, broker, or secret store not yet ready",
            "OOMKilled immediately after start due to insufficient memory limit",
            "Init script or database migration job failing with non-zero exit code",
            "Image entrypoint change in recent deployment introducing a startup regression",
        ],
        "diagnosis": [
            "Retrieve crash output: `kubectl logs <pod> --previous`",
            "Inspect init container logs: `kubectl logs <pod> -c <init-container>`",
            "Check exit code reason: `kubectl describe pod <pod>` → Last State section",
            "Verify all required secrets and configmaps are mounted and correctly populated",
            "Review `kubectl get events -n <ns>` for specific failure messages",
        ],
        "resolution": [
            "Fix misconfigured secrets or environment variables and redeploy",
            "Add init-container retry loops to wait for dependencies before main app starts",
            "Increase memory limit if OOMKilled is the identified exit reason",
            "Roll back to last known-good image if regression was introduced by recent deploy",
            "Long-term: add startup probe with sufficient failureThreshold for slow-starting apps",
        ],
        "escalation": "Escalate to release engineering if rollback fails or causes further instability. Engage security team if crash is caused by secret store access failure.",
    },
    "queue_buildup": {
        "display": "Queue / Backlog Buildup",
        "symptoms": [
            "{sys} queue depth or consumer lag growing faster than it is drained",
            "Producer applying backpressure to upstream services due to queue saturation",
            "Message TTL expiry causing data loss as lag grows beyond retention window",
            "Memory alarm triggered on {sys} broker as in-memory queue fills",
            "Downstream processing latency increasing under queue backlog pressure",
        ],
        "causes": [
            "Consumer processing speed lower than current producer publish rate",
            "Consumer group paused, crashed, or under-scaled relative to load",
            "Slow downstream dependency causing consumer thread blocking",
            "Traffic spike doubling producer rate with no corresponding consumer scale-out",
            "Consumer holding messages without acknowledging until slow processing completes",
        ],
        "diagnosis": [
            "Check queue depth or consumer lag metric over time for sustained growth trend",
            "Verify consumer instances are running and actively processing messages",
            "Identify the slowest step in consumer pipeline using distributed APM traces",
            "Compare producer publish rate vs consumer throughput over the last 1 hour",
            "Check consumer error rate for indication of processing failures causing requeuing",
        ],
        "resolution": [
            "Immediate: scale out consumer group to match or exceed producer publish rate",
            "Fix slow or failing processing step in the consumer pipeline",
            "Enable flow control or backpressure on producer if drain will take > SLA window",
            "Increase consumer batch size or prefetch count to improve throughput",
            "Long-term: add queue depth alerting at 50K messages and auto-scaling trigger",
        ],
        "escalation": "Escalate to data platform team if consumer scale-out does not drain backlog within SLO window. Escalate immediately if TTL expiry confirms data loss in production.",
    },
}


def _problem_display(pid: str) -> str:
    return " ".join(w.capitalize() for w in pid.replace("_", " ").split())


def _get_prob(pid: str) -> dict:
    if pid in _PROBLEMS:
        return _PROBLEMS[pid]
    # Generic fallback for less-common problem types
    display = _problem_display(pid)
    return {
        "display": display,
        "symptoms": [
            "{sys} showing degraded performance consistent with {display} condition",
            "Service error rate elevated in {sys} monitoring dashboard",
            "On-call alert: {sys} {display} threshold exceeded in production",
            "Downstream dependent services reporting elevated latency from {sys}",
        ],
        "causes": [
            "Misconfiguration introduced during recent change window for {sys}",
            "Capacity limit reached due to growth beyond original capacity estimate",
            "Dependency failure propagating to {sys} via tight coupling",
            "Software defect or regression exposed by increased load",
        ],
        "diagnosis": [
            "Check {sys} error logs around incident start time for recurring patterns",
            "Review recent configuration changes deployed to {sys} in the last 24 hours",
            "Inspect {sys} metrics dashboard for anomalies relative to 7-day baseline",
            "Run {sys} health check utility to enumerate the current error state",
        ],
        "resolution": [
            "Immediate: apply {sys} emergency configuration to stabilise the service",
            "Short-term: implement the workaround documented in the {sys} vendor runbook",
            "Validate: confirm {sys} metrics return to baseline after remediation applied",
            "Long-term: address root cause via infrastructure change or code fix",
        ],
        "escalation": "Escalate to {sys} vendor support or on-call architect if resolution is not achieved within the SLO response window.",
        "display_name": display,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3.  CONTENT POOLS (for incident parameterisation)
# ─────────────────────────────────────────────────────────────────────────────

_SERVICES = [
    "auth-service",        "api-gateway",          "payment-processor",
    "order-service",       "inventory-manager",     "notification-service",
    "user-profile-api",    "product-catalog",       "recommendation-engine",
    "search-api",          "checkout-service",      "fulfillment-service",
    "shipping-tracker",    "pricing-engine",         "fraud-detector",
    "reporting-service",   "analytics-pipeline",    "event-ingestor",
    "webhook-dispatcher",  "session-manager",        "cache-warmer",
    "data-sync-job",       "batch-processor",       "etl-worker",
    "ml-inference-api",    "config-service",         "feature-flags",
    "audit-logger",        "metrics-exporter",      "scheduler-daemon",
    "document-store-api",  "media-transcoder",      "email-gateway",
    "sms-router",          "push-notification-api", "file-upload-service",
    "image-resizer",       "pdf-generator",         "export-service",
    "import-validator",    "data-retention-worker", "backup-orchestrator",
    "key-rotation-service","token-vending-machine", "rate-limiter",
    "circuit-breaker-proxy","request-router",       "tenant-manager",
    "billing-processor",   "subscription-service",  "health-aggregator",
]

_ENVS = [
    "production", "production-eu", "production-ap", "production-us",
    "staging", "dr-primary", "dr-secondary",
]

_REGIONS = [
    "us-east-1", "us-west-2", "eu-west-1", "eu-central-1",
    "ap-southeast-1", "ap-northeast-1", "ca-central-1",
]

_SEVERITIES = [
    # (code, label, impact_phrase, sla_breach_threshold_min)
    ("P1", "Critical", "all production",         30),
    ("P2", "High",     "a significant subset of",  90),
    ("P3", "Medium",   "a limited number of",     240),
]

_ENGINEERS = [
    "Alice Chen",      "Bob Martinez",    "Carol Singh",    "David Kim",
    "Elena Zhou",      "Frank Okonkwo",   "Grace Tanaka",   "Henry Patel",
    "Iris Nakamura",   "James O'Brien",   "Karen Liu",      "Liam Nguyen",
    "Maya Sharma",     "Noah Williams",   "Olivia Brown",   "Peter Vasquez",
    "Quinn Adams",     "Rachel Fernandez","Sam Taylor",      "Tara Johnson",
]

_HOW_TO_OPS = [
    "Monitor",  "Scale",    "Configure", "Back Up",  "Restore",
    "Upgrade",  "Tune",     "Secure",    "Debug",    "Integrate",
]

_HOW_TO_CONTEXTS = [
    "in production",              "in Kubernetes",
    "with high availability",     "with Prometheus metrics",
    "for disaster recovery",      "at scale",
    "with security hardening",    "after a major upgrade",
    "for performance optimisation","using Terraform",
]

_BASE_DATE = datetime.date(2023, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(s: str, sys_name: str, display: str = "") -> str:
    """Substitute {sys} and {display} placeholders."""
    return s.replace("{sys}", sys_name).replace("{display}", display)


def _generate_runbook(sys_dict: dict, problem_id: str) -> dict:
    prob = _get_prob(problem_id)
    sys_name = sys_dict["display"]
    display  = prob["display"]

    def section(items: list[str], numbered: bool = False) -> str:
        lines = []
        for i, item in enumerate(items):
            text = _fmt(item, sys_name, display)
            lines.append(f"{i+1}. {text}" if numbered else f"- {text}")
        return "\n".join(lines)

    text = (
        f"## Runbook: {sys_name} — {display}\n\n"
        f"**Category**: {sys_dict['cat'].replace('_', ' ').title()}  "
        f"**System**: {sys_name}  "
        f"**Problem**: {display}\n\n"
        f"### Symptoms\n{section(prob['symptoms'])}\n\n"
        f"### Root Causes\n{section(prob['causes'])}\n\n"
        f"### Diagnosis Steps\n{section(prob['diagnosis'], numbered=True)}\n\n"
        f"### Resolution Steps\n{section(prob['resolution'], numbered=True)}\n\n"
        f"### Escalation\n{_fmt(prob['escalation'], sys_name, display)}\n"
    )

    return {
        "chunk_id":  f"RB-{sys_dict['id']}-{problem_id}",
        "doc_id":    f"RB-{sys_dict['id']}-{problem_id}",
        "title":     f"Runbook: {sys_name} — {display}",
        "source":    "runbook",
        "text":      text,
        "tags":      [sys_dict["id"], problem_id, sys_dict["cat"], "runbook"],
        "tenant_id": "default",
    }


def _generate_incident(idx: int, rng: random.Random) -> dict:
    sys_dict              = rng.choice(_SYSTEMS)
    problem_id            = rng.choice(sys_dict["problems"])
    prob                  = _get_prob(problem_id)
    sev_code, sev_label, impact_phrase, sla_min = rng.choice(_SEVERITIES)
    service               = rng.choice(_SERVICES)
    env                   = rng.choice(_ENVS)
    region                = rng.choice(_REGIONS)

    day_offset  = rng.randint(0, 729)          # 2 years of history
    date        = _BASE_DATE + datetime.timedelta(days=day_offset)
    hour        = rng.randint(0, 23)
    minute      = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])

    # Duration varies by severity
    if sev_code == "P1":
        duration_min = rng.randint(10, 90)
    elif sev_code == "P2":
        duration_min = rng.randint(30, 180)
    else:
        duration_min = rng.randint(60, 480)

    h_dur, m_dur = divmod(duration_min, 60)
    dur_str = (f"{h_dur}h {m_dur}m" if h_dur else f"{m_dur}m")

    # Impact metrics
    user_count   = rng.choice([50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000])
    error_pct    = rng.randint(5, 99)
    baseline_pct = rng.choice([0.1, 0.2, 0.5, 1.0])
    latency_p99  = rng.randint(250, 30_000)
    baseline_lat = rng.randint(50, 400)

    eng1, eng2 = rng.sample(_ENGINEERS, 2)
    sys_name   = sys_dict["display"]
    display    = prob["display"]

    # Timeline deltas (minutes from incident open)
    d_page   = rng.randint(2, 8)
    d_triage = rng.randint(10, 25)
    d_rca    = rng.randint(25, max(26, duration_min // 2))
    d_fix    = rng.randint(d_rca + 5, max(d_rca + 6, duration_min - 3))

    def ts(delta_min: int) -> str:
        total = hour * 60 + minute + delta_min
        return f"{date} {(total // 60) % 24:02d}:{total % 60:02d} UTC"

    root_cause   = _fmt(rng.choice(prob["causes"]),     sys_name, display)
    resolution   = _fmt(rng.choice(prob["resolution"]), sys_name, display)

    sla_note = (
        f" SLA breach recorded — duration {dur_str} exceeded {sla_min}m threshold."
        if duration_min > sla_min else ""
    )

    root_cause_long = (
        f"Post-incident analysis confirmed: {root_cause.lower()}. "
        f"The condition manifested in {env} ({region}) for the {service} on "
        f"{date.strftime('%Y-%m-%d')} at {hour:02d}:{minute:02d} UTC. "
        f"Key signals: error rate rose to {error_pct}% (baseline {baseline_pct}%) "
        f"and p99 latency climbed to {latency_p99}ms (baseline {baseline_lat}ms). "
        f"The {sys_name} {display} condition propagated to dependent {service} "
        f"endpoints within {d_triage} minutes of onset."
    )
    resolution_long = (
        f"{resolution}. "
        f"Engineers {eng1} and {eng2} co-ordinated the response on the incident bridge. "
        f"Service metrics confirmed full recovery {dur_str} after initial alert. "
        f"Error rate returned to {baseline_pct}% and p99 latency to {baseline_lat}ms."
    )
    followup = [
        _fmt(rng.choice(prob["resolution"]), sys_name, display),
        f"Update runbook for {display} on {sys_name} with lessons from this incident",
        f"Lower MTTD for {sys_name} {display} alerts by tightening threshold by 20%",
    ]

    text = (
        f"INC-{idx:06d} | {sev_code} — {sev_label} | {sys_name} :: {display}\n"
        f"Service: {service} | Environment: {env} | Region: {region}\n"
        f"Opened: {ts(0)} | Duration: {dur_str} | Responders: {eng1}, {eng2}\n\n"
        f"IMPACT\n"
        f"Approximately {user_count:,} {impact_phrase} users affected by {sys_name} "
        f"degradation. Error rate elevated to {error_pct}% (baseline: {baseline_pct}%). "
        f"p99 latency: {latency_p99}ms (baseline: {baseline_lat}ms).{sla_note}\n\n"
        f"INCIDENT TIMELINE\n"
        f"{ts(0)} — Alert fired: {sys_name} {display} threshold exceeded\n"
        f"{ts(d_page)} — On-call paged via PagerDuty; incident bridge opened by {eng1}\n"
        f"{ts(d_triage)} — Initial triage: upstream dependencies ruled out\n"
        f"{ts(d_rca)} — Root cause confirmed: {root_cause}\n"
        f"{ts(d_fix)} — Remediation applied: {resolution}\n"
        f"{ts(duration_min)} — Service metrics restored to baseline; incident closed\n\n"
        f"ROOT CAUSE ANALYSIS\n{root_cause_long}\n\n"
        f"REMEDIATION TAKEN\n{resolution_long}\n\n"
        f"FOLLOW-UP ACTIONS\n"
        + "\n".join(f"{i+1}. {fu}" for i, fu in enumerate(followup))
        + "\n"
    )

    return {
        "chunk_id":  f"INC-{idx:06d}",
        "doc_id":    f"INC-{idx:06d}",
        "title":     f"Incident {idx:06d}: {sev_code} {sys_name} {display} in {env}",
        "source":    "incident",
        "text":      text,
        "tags":      [sys_dict["id"], problem_id, sev_code.lower(),
                      env.split("-")[0], sys_dict["cat"]],
        "tenant_id": "default",
    }


def _generate_howto(idx: int, rng: random.Random) -> dict:
    sys_dict  = rng.choice(_SYSTEMS)
    operation = rng.choice(_HOW_TO_OPS)
    context   = rng.choice(_HOW_TO_CONTEXTS)
    sys_name  = sys_dict["display"]
    cat_label = sys_dict["cat"].replace("_", " ")
    env_ex    = rng.choice(_ENVS)
    region_ex = rng.choice(_REGIONS)

    prereqs = [
        f"Operator-level access to the {sys_name} admin interface or CLI",
        f"Familiarity with {cat_label} fundamentals and {sys_name} architecture",
        f"Valid credentials stored in Vault for the target {env_ex} environment",
        f"Observability dashboard access (Grafana, Prometheus) to verify changes",
    ]

    steps = [
        f"Verify the current state of {sys_name} {context} using the status command",
        f"Review {sys_name} configuration files and confirm environment is {env_ex} ({region_ex})",
        f"Apply the required {operation.lower()} procedure following the {sys_name} operator guide",
        f"Monitor {sys_name} metrics in Grafana for at least 10 minutes after the change",
        f"Check application error rate and latency via APM to confirm no regression",
        f"Update the change log in the internal wiki with the applied {operation.lower()} steps",
        f"Notify dependent teams via the #{sys_dict['id']}-ops Slack channel",
    ]

    pitfalls = [
        f"Do not {operation.lower()} {sys_name} during peak traffic; schedule in the maintenance window",
        f"Always take a snapshot or backup before any {operation.lower()} that modifies {sys_name} data",
        f"Confirm quorum or replication health before proceeding if {sys_name} is clustered",
    ]

    text = (
        f"## How to {operation} {sys_name} {context}\n\n"
        f"### Overview\n"
        f"This guide covers how to {operation.lower()} {sys_name} {context}. "
        f"It is intended for {cat_label} engineers and SREs responsible for "
        f"{sys_name} operations in enterprise environments.\n\n"
        f"### When to Use This Guide\n"
        f"Use this guide when you need to {operation.lower()} {sys_name} {context} "
        f"as part of standard operations, planned maintenance, or incident response.\n\n"
        f"### Prerequisites\n"
        + "\n".join(f"- {p}" for p in prereqs)
        + f"\n\n### Procedure\n"
        + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
        + f"\n\n### Verification\n"
        f"After completing the procedure, confirm {sys_name} is healthy: check the "
        f"service-level metrics in Grafana, verify the {sys_name} status endpoint "
        f"returns expected output, and ensure downstream {sys_name} consumers show "
        f"no elevated error rate for at least 5 minutes.\n\n"
        f"### Common Pitfalls\n"
        + "\n".join(f"- {p}" for p in pitfalls)
        + "\n"
    )

    return {
        "chunk_id":  f"HT-{idx:06d}",
        "doc_id":    f"HT-{idx:06d}",
        "title":     f"How to {operation} {sys_name} {context}",
        "source":    "kb_article",
        "text":      text,
        "tags":      [sys_dict["id"], operation.lower().replace(" ", "_"),
                      sys_dict["cat"], "how_to"],
        "tenant_id": "default",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5.  CORPUS BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_corpus(
    n_incidents: int = 9_000,
    n_howtos: int    = 3_000,
    seed: int        = 42,
) -> list[dict]:
    rng = random.Random(seed)
    chunks: list[dict] = []

    # Runbooks — one per (system, problem) pair
    for sys_dict in _SYSTEMS:
        for problem_id in sys_dict["problems"]:
            chunks.append(_generate_runbook(sys_dict, problem_id))

    n_runbooks = len(chunks)
    print(f"  Runbooks generated : {n_runbooks}")

    # Incident histories
    for i in range(n_incidents):
        chunks.append(_generate_incident(i + 1, rng))
    print(f"  Incidents generated: {n_incidents}")

    # How-to articles
    for i in range(n_howtos):
        chunks.append(_generate_howto(i + 1, rng))
    print(f"  How-tos generated  : {n_howtos}")

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# 6.  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build large-scale IT Ops corpus and FAISS/BM25 indexes."
    )
    parser.add_argument("--incidents",   type=int, default=9_000,
                        help="Number of synthetic incident records (default: 9000)")
    parser.add_argument("--howtos",      type=int, default=3_000,
                        help="Number of how-to articles (default: 3000)")
    parser.add_argument("--seed",        type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--index-dir",   default="data/index",
                        help="Output directory for FAISS index (default: data/index)")
    parser.add_argument("--lexical-dir", default="data/lexical",
                        help="Output directory for BM25 index (default: data/lexical)")
    args = parser.parse_args()

    print("=" * 60)
    print("Large-scale IT Ops corpus builder")
    print("=" * 60)
    print(f"  incidents  : {args.incidents:,}")
    print(f"  how-tos    : {args.howtos:,}")
    print(f"  seed       : {args.seed}")
    print(f"  index-dir  : {args.index_dir}")
    print(f"  lexical-dir: {args.lexical_dir}")
    print()

    print("Generating corpus...")
    chunks = build_corpus(
        n_incidents=args.incidents,
        n_howtos=args.howtos,
        seed=args.seed,
    )
    total = len(chunks)
    print(f"  Total documents    : {total:,}")
    print()

    print(
        f"Building vector index (embedding {total:,} documents — "
        "this may take several minutes on CPU)..."
    )
    vs = VectorStore(args.index_dir)
    vs.build(chunks)
    vs.save()
    index_type = "IndexHNSWFlat" if total >= 10_000 else "IndexFlatIP"
    print(f"  Vector index saved : {vs.size:,} vectors → {index_type}")
    print(f"  Output             : {args.index_dir}/")
    print()

    print("Building BM25 lexical index...")
    ls = LexicalStore(args.lexical_dir)
    ls.build(chunks)
    ls.save()
    print(f"  BM25 index saved   : {total:,} documents")
    print(f"  Output             : {args.lexical_dir}/")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
