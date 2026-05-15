#!/bin/bash
# nexus/infra/kafka/create_topics.sh
# Creates all NEXUS Kafka topics with correct partition and retention settings.
# Run via: docker compose exec kafka /bin/bash /create_topics.sh
#
# WINDOWS NOTE: This file MUST have LF line endings (enforced by .gitattributes).
# If you see '/bin/bash^M: bad interpreter', the file has CRLF endings.
# Fix: git add --renormalize infra/kafka/create_topics.sh && git commit

set -e

BOOTSTRAP="localhost:9092"
REPLICATION_FACTOR=1 # For production, set this to the number of Kafka brokers in your cluster.

echo "Creating NEXUS Kafka topics..."

# nexus.tasks - orchestrator -> agents (task dispatch)
# 4 partitions: one per agent type (search, code, memory, tool)

kafka-topics \
    --bootstrap-server "$BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic nexus.tasks \
    --partitions 4 \
    --replication-factor "$REPLICATION_FACTOR" \
    --config retention.ms=864000000 \
    --config max.message.bytes=1048576

# nexus.results - agents -> orchestrator (task results)
# 4 partitions: matches nexus.tasks for ordering guarantees

kafka-topics \
    --bootstrap-server "$BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic nexus.results \
    --partitions 4 \
    --replication-factor "$REPLICATION_FACTOR" \
    --config retention.ms=864000000 \
    --config max.message.bytes=1048576

# nexus.events - orchestrator -> SSE emitter (through trace events)
# 1 partition: SSE delivery is per-run, ordering must be strict

kafka-topics \
    --bootstrap-server "$BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic nexus.events \
    --partitions 1 \
    --replication-factor "$REPLICATION_FACTOR" \
    --config retention.ms=3600000 \
    --config max.message.bytes=524288

echo "Verifying topics were created..."

kafka-topics \
    --bootstrap-server "$BOOTSTRAP" --list

echo "NEXUS topics creation complete."
