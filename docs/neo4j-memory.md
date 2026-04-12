# Neo4j Memory Architecture

The Development Harness includes an optional graph-based persistent memory system using Neo4j. This is the knowledge layer that lets agents query accumulated project knowledge dynamically, rather than stuffing everything into context windows.

---

## Dual-Database Architecture

The harness uses two databases with complementary roles:

| Database | Role | What It Stores |
|----------|------|----------------|
| **SQLite** | Hot operational state | Active threads, in-flight events, config, credentials, approval requests |
| **Neo4j** | Accumulated knowledge graph | Decisions, patterns, debugging history, relationships, code structure, summaries |

Data flows one direction: **SQLite -> Neo4j** via an asynchronous ingestion pipeline. Neo4j never writes back to SQLite. This means Neo4j is a derived view of the operational data, enriched with semantic relationships and embeddings.

```
Harness Runtime
    |
    |-- SQLite (operational state, event log, config)
    |       |
    |       v
    |   Ingestion Pipeline (async, non-blocking, batched)
    |       |
    |       v
    +-- Neo4j (knowledge graph + vector indexes)
            ^
            |
        Agent queries (memory_query, memory_search, memory_traverse tools)
```

---

## Graph Schema

### Node Types

The knowledge graph contains approximately 30 node types organized into categories:

**Operational Nodes:**

| Node | Description |
|------|-------------|
| `Project` | A project workspace |
| `Session` | A harness session |
| `Thread` | A thread of execution |
| `Turn` | A single turn within a thread |
| `Prompt` | A user or harness prompt |
| `AgentResponse` | An agent's response |
| `Plan` | A task decomposition plan |
| `PlanStep` | A step within a plan |
| `ToolCall` | A tool invocation |
| `ToolResult` | The result of a tool call |
| `Artifact` | A generated artifact (patch, screenshot, report) |

**Code Structure Nodes:**

| Node | Description |
|------|-------------|
| `CodeFile` | A source file |
| `Module` | A Python module or package |
| `Function` | A function or method |
| `Class` | A class definition |

**Knowledge Nodes:**

| Node | Description |
|------|-------------|
| `ArchitectureDecision` | A recorded architecture decision (ADR) |
| `DesignPrinciple` | A design principle or pattern |
| `Constraint` | A project constraint |
| `Concept` | A domain concept |
| `Topic` | A discussion topic |

**Error Tracking Nodes:**

| Node | Description |
|------|-------------|
| `Error` | An error occurrence |
| `DebugAttempt` | A debugging attempt |
| `Fix` | A fix applied to resolve an error |

**Verification Nodes:**

| Node | Description |
|------|-------------|
| `VerificationResult` | Result of a verifier |
| `TestResult` | Test execution result |
| `Observation` | An observer finding |

**Summary Nodes:**

| Node | Description |
|------|-------------|
| `SessionSummary` | Summary of a session |
| `DailySummary` | Daily activity summary |
| `WeeklySummary` | Weekly aggregate summary |
| `MonthlySummary` | Monthly aggregate summary |

### Relationship Types

The graph uses approximately 30+ relationship types organized by function:

**Structural Containment:**

```
Project -[CONTAINS_PROJECT]-> Session
Session -[HAS_SESSION]-> Thread
Thread  -[HAS_THREAD]-> Turn
Module  -[CONTAINS_FILE]-> CodeFile
CodeFile -[DEFINES_CLASS]-> Class
CodeFile -[DEFINES_FUNCTION]-> Function
```

**Temporal Ordering:**

```
Turn -[PRECEDED]-> Turn
Turn -[FOLLOWED]-> Turn
DailySummary -[NEXT_DAY]-> DailySummary
```

**Causal/Operational:**

```
Turn -[CONTAINS_PROMPT]-> Prompt
Turn -[PRODUCED_PLAN]-> Plan
Plan -[EXECUTED_AS]-> PlanStep
ToolCall -[MODIFIED_FILE]-> CodeFile
ToolCall -[CREATED_FILE]-> CodeFile
Turn -[PRODUCED_ARTIFACT]-> Artifact
```

**Error Chains:**

```
Turn -[SURFACED_ERROR]-> Error
Error -[TRIGGERED_DEBUG]-> DebugAttempt
DebugAttempt -[ATTEMPTED_FIX]-> Fix
Fix -[RESOLVED]-> Error
Error -[SIMILAR_TO]-> Error
```

**Verification:**

```
Turn -[VERIFIED_BY]-> VerificationResult
VerificationResult -[INCLUDES_TEST]-> TestResult
TestResult -[TESTS_FILE]-> CodeFile
```

**Knowledge:**

```
Turn -[DISCUSSES]-> Concept
ArchitectureDecision -[ABOUT]-> Module
ArchitectureDecision -[AFFECTS_MODULE]-> Module
Constraint -[CONSTRAINED_BY]-> Module
DesignPrinciple -[EMBODIES]-> Module
```

**Summarization:**

```
SessionSummary -[SUMMARIZES_SESSION]-> Session
DailySummary -[SUMMARIZES_DAY]-> Turn  (multiple)
WeeklySummary -[AGGREGATES]-> DailySummary (multiple)
```

---

## Memory Ingestion Pipeline

Events flow from the harness runtime to Neo4j through an asynchronous, non-blocking pipeline.

### Buffering

Events are buffered before flushing to Neo4j:

- **Time-based:** Flush every 5 seconds.
- **Count-based:** Flush when 50 events accumulate.
- Whichever threshold is hit first triggers a flush.

Buffering reduces Neo4j write pressure and allows batching into efficient Cypher transactions.

### Batched Cypher Transactions

Each flush sends a batch of events as a single Cypher transaction. This is significantly faster than individual writes:

```cypher
UNWIND $events AS event
MERGE (t:Turn {id: event.turn_id})
CREATE (tc:ToolCall {id: event.id, tool_name: event.tool_name})
CREATE (t)-[:EXECUTED]->(tc)
```

### Embedding Generation

Vector embeddings are generated asynchronously for nodes that benefit from semantic search:

- Prompts
- Errors
- Artifacts
- CodeFiles
- ArchitectureDecisions
- Concepts
- All Summary types

The default embedding model is `text-embedding-3-small` (OpenAI) with 1536 dimensions. This is configurable via `HarnessConfig.embedding_model` and `HarnessConfig.embedding_dimensions`.

### Vector Indexes

Neo4j vector indexes are created on embedding-enabled node types for fast approximate nearest-neighbor search.

---

## Agent Query Tools

The memory system exposes three tools to the agent:

### memory_query

Structured Cypher queries with pre-built query types:

```
memory_query(
    query_type="architecture_decisions",
    filters={"module": "auth"},
    max_results=10,
)
```

Available query types:

| Type | Description |
|------|-------------|
| `architecture_decisions` | ADRs affecting a module or topic |
| `error_history` | Past errors with similar patterns |
| `fix_history` | Fixes applied for a class of errors |
| `file_history` | Changes made to a specific file |
| `session_summary` | Summary of a past session |
| `daily_summary` | Summary of a specific day |
| `concept_map` | Related concepts and their connections |
| `module_dependencies` | Module-level dependency graph |

### memory_search

Vector similarity search with optional graph expansion:

```
memory_search(
    text="authentication timeout handling",
    scope="decisions",
    max_results=5,
)
```

The search finds semantically similar nodes using vector embeddings, then optionally expands along graph relationships to surface related knowledge.

### memory_traverse

Walk the graph from a starting point along typed relationships:

```
memory_traverse(
    start_node="error:auth_timeout_abc123",
    relationship_types=["TRIGGERED_DEBUG", "ATTEMPTED_FIX", "RESOLVED"],
    depth=3,
)
```

This is useful for tracing error chains: what was tried, what worked, what did not.

---

## GraphRAG Retrieval

The memory system uses a hybrid retrieval strategy combining vector search and graph traversal:

1. **Vector search** finds semantically similar entry points (nodes whose embeddings are close to the query).
2. **Graph traversal** expands from those entry points along typed relationships.
3. **Hybrid scoring** ranks results:

```
score = 0.5 * vector_similarity + 0.3 * (1 / graph_distance) + 0.2 * recency_score
```

This produces richer results than pure vector search. A question about "how we handled auth timeouts" finds not just semantically similar text, but also the specific error, the debug attempts, and the fix that resolved it.

---

## Daily Consolidation

At 3:00 AM (configurable via `HarnessConfig.consolidation_schedule`), a consolidation job runs:

1. **Gather raw events** for the day from SQLite.
2. **Generate session summaries** using a lightweight model (Haiku or Sonnet).
3. **Extract architecture decisions** from agent conversations.
4. **Extract recurring problems** and their resolution patterns.
5. **Extract concepts and topics** discussed during the day.
6. **Build a DailySummary node** linking to all relevant events and summaries.
7. **Weekly/monthly rollup** on schedule (weekly on Sunday, monthly on the 1st).

This consolidation converts raw event data into structured knowledge that is cheaper to query and more useful for long-term retrieval.

---

## Time-Based Tiers

Knowledge in the graph is organized into temporal tiers for scaling:

| Tier | Age | Content |
|------|-----|---------|
| Hot | 0-7 days | Full detail: all events, tool calls, observations |
| Warm | 7-90 days | Session summaries, architecture decisions, error patterns |
| Cool | 90-365 days | Daily/weekly summaries, key decisions |
| Cold | >365 days | Monthly summaries, architectural landmarks |

Raw event detail nodes are pruned during weekly maintenance. Summary nodes persist. This keeps the graph size manageable while preserving essential knowledge.

---

## Graceful Degradation

Neo4j is an enhancement, not a dependency. The harness works identically with or without it.

### When Neo4j Is Available

- Events are ingested into the graph via the async pipeline.
- Agent memory tools return rich results.
- Consolidation runs on schedule.

### When Neo4j Is Unavailable

- Events are buffered in SQLite (`buffer_memory_event`).
- Memory query tools return empty results.
- The agent continues working normally.
- No error messages reach the agent.

### When Neo4j Comes Back

- The SQLite buffer is drained and replayed into Neo4j.
- Events are processed in order, preserving causality.
- The buffer is cleared after successful replay.

This design means Neo4j can go down for maintenance, restart, or be temporarily unavailable without any impact on the agent's ability to work.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USERNAME` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | | Neo4j password |
| `DEVHARNESS_MEMORY_BACKEND` | `none` | Set to `neo4j` to enable |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model for vector embeddings |

### HarnessConfig Fields

```python
class HarnessConfig(BaseModel):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_database: str = "harness"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_enabled: bool = False
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    consolidation_schedule: str = "0 3 * * *"  # cron: 3 AM daily
```

### Running Neo4j

Docker is the simplest way:

```bash
docker run \
  --name neo4j-harness \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  -v neo4j-data:/data \
  neo4j:5
```

Then configure:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=your-password
export DEVHARNESS_MEMORY_BACKEND=neo4j
```

### Python Dependencies

```bash
pip install devharness[memory-neo4j]
```

---

## Obsidian as Alternative

For users who prefer a file-based, human-readable knowledge system, the harness supports an Obsidian vault as an alternative memory backend. The vault uses Markdown files with YAML frontmatter.

See the `ObsidianMemoryBackend` class in `memory/obsidian/backend.py`.

**Tradeoffs:**

| Aspect | Neo4j | Obsidian |
|--------|-------|---------|
| Relationship queries | Native, fast multi-hop | Slower (file traversal + link parsing) |
| Vector search | Native vector indexes | Requires external embedding + search |
| Human readability | Requires Neo4j Browser | Readable in any editor |
| Infrastructure | Docker or install required | Zero -- just files |
| Git-friendly | Not directly | Fully diffable, versionable |
| Scale | Handles 100K+ nodes | Best for under 10K files |

Both implement the same `MemoryBackend` interface. Switch between them via `DEVHARNESS_MEMORY_BACKEND`.
