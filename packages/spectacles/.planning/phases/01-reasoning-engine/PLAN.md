# Spectacles → Spectacles: AI Reasoning Engine Implementation

**Plan ID:** `SPECTICALES_REASONING_ENGINE_V2_PM_ORCHESTRATED`
**Created:** 2026-01-19
**Revised:** 2026-01-20 (v2: Added Phase 0, PM orchestration, Qdrant isolation)
**Status:** Ready for Autonomous Execution
**Complexity:** High (Core Architecture Change + Rename)
**Execution Mode:** Fully Autonomous (PM Agent + Supervising Agents)

---

## Executive Summary

This plan transforms **Spectacles** (misspelled) into **Spectacles** (correct spelling) while simultaneously upgrading it from a perception-driven automation tool to an intelligent learning agent.

**Two Major Goals:**
1. **Phase 0:** Rename project from "spectacles" to "spectacles" across all systems
2. **Phases 1-4:** Implement AI Reasoning Engine with memory-based pattern learning

**Key Innovation:** Fully autonomous execution via hierarchical agent structure - Project Manager spawns specialized supervising agents for each phase, requiring zero user intervention.

**Performance Target:** 5-10x speed improvement + 80%+ cost reduction on repeated tasks.

---

## PM Agent Orchestration Structure

### Hierarchical Agent Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      PROJECT MANAGER AGENT                       │
│  • Oversees entire plan execution (Phases 0-4)                  │
│  • Spawns supervising agents for each phase                     │
│  • Validates between phases (replaces human checkpoints)        │
│  • Handles blockers and escalation                              │
│  • Creates final SUMMARY.md                                     │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├─► Phase 0 Supervising Agent: REFACTOR SPECIALIST
             │   ├─ Rename all code/configs (297 references)
             │   ├─ Migrate GCP secrets (11 secrets)
             │   ├─ Update directory structure
             │   ├─ Verify tests pass
             │   └─ Report: Rename complete → PM validates
             │
             ├─► Phase 1 Supervising Agent: AI INTEGRATION SPECIALIST
             │   ├─ Implement AI Reasoner Core
             │   ├─ Integrate with Gemini API
             │   ├─ Write unit tests
             │   └─ Report: Reasoner ready → PM validates
             │
             ├─► Phase 2 Supervising Agent: DATABASE SPECIALIST
             │   ├─ Implement Qdrant Pattern Store
             │   ├─ Implement Embeddings Service
             │   ├─ Write unit + integration tests
             │   └─ Report: Pattern store ready → PM validates
             │
             ├─► Phase 3 Supervising Agent: BACKEND ARCHITECT
             │   ├─ Implement Pattern Extraction Engine
             │   ├─ Pattern classification logic
             │   ├─ Write unit tests
             │   └─ Report: Extractor ready → PM validates
             │
             └─► Phase 4 Supervising Agent: BACKEND ARCHITECT
                 ├─ Implement Learning Integration
                 ├─ Orchestrator hooks + confidence tracking
                 ├─ Write integration tests
                 └─ Report: Implementation complete → PM validates
```

### PM Agent Responsibilities

**Pre-Execution:**
1. ✅ Create `spectacles-google-ai-api-key` (already done)
2. ✅ Validate embedding model before Phase 2
3. ✅ Verify environment setup

**During Execution (Per Phase):**
1. Spawn supervising agent for phase
2. Monitor agent progress
3. Handle agent-reported blockers
4. Validate phase completion via automated tests
5. Review code changes
6. Approve progression to next phase

**Post-Execution:**
1. Run full test suite (25+ unit, 6+ integration)
2. Build Docker image + smoke tests
3. Create comprehensive SUMMARY.md
4. Report final status to user

### Autonomous Decision Authority

**PM Agent CAN decide autonomously:**
- ✅ Architecture implementation details (within plan scope)
- ✅ Code structure and patterns
- ✅ Error handling strategies
- ✅ Performance optimizations
- ✅ Auto-fix deviations (bugs, missing validation, blockers)
- ✅ Alternative approaches if primary fails (e.g., alternative embedding model)
- ✅ Test strategies and coverage

**PM Agent MUST escalate:**
- ❌ New database tables or schema changes (beyond `learned_patterns`)
- ❌ Breaking API changes
- ❌ New external dependencies (beyond plan-approved ones)
- ❌ Major architectural deviations from plan
- ❌ Unresolvable blockers after 3 attempts

---

## Objective

Transform **Spectacles** into **Spectacles** while adding AI reasoning capabilities:

1. **Rename Project** - Fix spelling error across all systems
2. **AI Reasoning Layer** - Strategic task planning using LLM reasoning
3. **Memory Query System** - Pattern retrieval from Qdrant (fully isolated)
4. **Pattern Extraction** - Learning from successful task executions
5. **Confidence System** - Track pattern success/failure rates for adaptive behavior

**Success Means:**
- Correctly spelled "spectacles" across all systems
- Recognizes repeated tasks, retrieves patterns, executes without VLM calls
- 5-10x speed improvement + 80%+ cost reduction on known sites

---

## Current State Analysis

### What Works Today
- ✅ Gemini Vision AI for visual perception (VLMPerceiver)
- ✅ Playwright browser automation (BrowserSpecialist)
- ✅ State machine lifecycle management
- ✅ Database schema for `learned_patterns` table
- ✅ Production service deployed on Cloud Run

### Critical Gaps
- ❌ **Project name misspelled** - "spectacles" should be "spectacles"
- ❌ **Shared resources** - Using OUSD Pinecone API key
- ❌ **No reasoning layer** - Planning is hardcoded (orchestrator.py:361)
- ❌ **No memory queries** - No vector database integration
- ❌ **No pattern extraction** - Successful tasks don't contribute to learning
- ❌ **No confidence tracking** - `success_count`/`failure_count` fields never updated

### Current Task Flow (Inefficient)
```
User: "Login to example.com"
  ↓
Hardcoded Plan: [navigate, observe, achieve_goal]
  ↓
VLM Call #1: "Where's login button?" ($0.01, 2s)
VLM Call #2: "Where's username field?" ($0.01, 2s)
VLM Call #3: "Where's password field?" ($0.01, 2s)
... (5-8 VLM calls total)
  ↓
Total: $0.05-0.08, 20-30 seconds
```

### Target Flow (Intelligent + Correctly Named)
```
User: "Login to example.com"
  ↓
AI Reasoner: "Have I done this before?"
  ↓
Qdrant Query: Retrieve pattern from spectacles-memory
  ↓
Execute Pattern Directly (0 VLM calls, 3-5 seconds)
  ↓
Success → Increment pattern confidence
Failure → VLM fallback + Update pattern
  ↓
Total: $0.00-0.01, 3-5 seconds
```

---

## Isolated Architecture (No Shared Resources)

### New Stack Configuration

```
Spectacles (Fully Isolated)
├── Vector DB: Qdrant Embedded ✅ NEW
│   ├── Storage: ./qdrant_storage/
│   ├── Collection: spectacles-memory
│   ├── API Key: NONE (local mode)
│   ├── Cost: $0
│   └── Isolation: Complete (no shared resources)
│
├── LLM: Gemini 2.0 Flash
│   ├── API Key: spectacles-google-ai-api-key ✅ DEDICATED
│   ├── Billing: Separate from OUSD
│   ├── Cost: ~$0.001 per reasoner query
│   └── Isolation: Complete
│
├── Embeddings: sentence-transformers
│   ├── Model: all-MiniLM-L6-v2 (packaged in Docker)
│   ├── API Key: NONE (runs locally)
│   ├── Cost: $0
│   └── Isolation: Complete
│
└── Database: SQLite
    ├── Storage: ./spectacles.db
    ├── Cost: $0
    └── Isolation: Complete
```

**Dependencies Changed:**
```diff
- pinecone-client>=6.0.0
+ qdrant-client==1.7.0
+ sentence-transformers==2.3.1
```

---

## Phase 0: Project Rename (spectacles → spectacles)

**Supervising Agent:** Refactor Specialist
**Estimated Time:** 30-45 minutes
**Risk Level:** Low (reversible via git)

### Objectives

1. ✅ Rename all code references (297 occurrences)
2. ✅ Migrate GCP secrets (11 secrets)
3. ✅ Update directory structure
4. ✅ Update Cloud Run service name
5. ✅ Verify all tests pass after rename

### Rename Scope

**Code & Configuration (297 references):**
- Python modules: `import spectacles` → `import spectacles`
- Config values: `spectacles-memory` → `spectacles-memory`
- API paths: `/api/spectacles/` → `/api/spectacles/`
- Documentation: All `*.md` files
- Docker image names
- Environment variables

**GCP Secrets (11 to migrate):**
```
spectacles-browserless-token       → spectacles-browserless-token
spectacles-github-client-id        → spectacles-github-client-id
spectacles-github-client-secret    → spectacles-github-client-secret
spectacles-google-ai-api-key       → spectacles-google-ai-api-key
spectacles-secret-key              → spectacles-secret-key
spectacles-slack-app-token         → spectacles-slack-app-token
spectacles-slack-bot-token         → spectacles-slack-bot-token
spectacles-slack-client-id         → spectacles-slack-client-id
spectacles-slack-client-secret     → spectacles-slack-client-secret
spectacles-slack-signing-secret    → spectacles-slack-signing-secret
spectacles-slack-verification-token → spectacles-slack-verification-token
```

**File System:**
```
projects/spectacles/          → projects/spectacles/
spectacles.db                 → spectacles.db
./qdrant_storage/spectacles-* → ./qdrant_storage/spectacles-*
```

**Infrastructure (Cloud Run):**
```
Service: spectacles → spectacles
URL: spectacles-*.run.app → spectacles-*.run.app (will change)
```

### Implementation Steps

**Step 1: Code Rename (10 min)**
```bash
# Find and replace in all files
find . -type f \( -name "*.py" -o -name "*.md" -o -name "*.json" \
  -o -name "*.yaml" -o -name "*.yml" -o -name ".env" -o -name "Dockerfile" \) \
  -exec sed -i 's/spectacles/spectacles/g' {} +

# Case-sensitive replacements for class names
find . -type f -name "*.py" -exec sed -i 's/Spectacles/Spectacles/g' {} +
```

**Step 2: GCP Secrets Migration (10 min)**
```bash
# For each secret, copy value to new name
for old_name in spectacles-{browserless-token,github-client-id,...}; do
  new_name=$(echo $old_name | sed 's/spectacles/spectacles/')
  value=$(gcloud secrets versions access latest --secret="$old_name")
  echo "$value" | gcloud secrets create "$new_name" --data-file=-
done
```

**Step 3: Directory Rename (2 min)**
```bash
cd /home/vncuser/Desktop/Claude_Code/projects
mv spectacles spectacles
```

**Step 4: Update Git (3 min)**
```bash
git add -A
git commit -m "refactor: rename project from spectacles to spectacles

- Fix spelling error in project name
- Update all code references (297 occurrences)
- Migrate GCP secrets (11 secrets)
- Update directory structure

Breaking Changes:
- API paths changed
- Cloud Run service URL will change on next deploy"
```

**Step 5: Verification (10 min)**
```bash
# Verify no old references remain
grep -r "spectacles" . --exclude-dir=.git --exclude-dir=node_modules

# Verify imports work
python -c "import spectacles; print('Import successful')"

# Run tests
pytest tests/ -v
```

### Success Criteria

- ✅ Zero occurrences of "spectacles" in code (excluding git history)
- ✅ All GCP secrets migrated and accessible
- ✅ Directory renamed successfully
- ✅ All imports work correctly
- ✅ All existing tests pass
- ✅ Git history preserved

### PM Validation (Automated)

```python
# PM agent runs these checks:
checks = [
    "grep -r 'spectacles' . --exclude-dir=.git | wc -l == 0",
    "gcloud secrets describe spectacles-google-ai-api-key",
    "python -c 'import spectacles'",
    "pytest tests/ -v --tb=short"
]
# All must pass before Phase 1
```

---

## Phase 1: AI Reasoner Core

**Supervising Agent:** AI Integration Specialist
**Estimated Time:** 2-3 hours
**Dependencies:** Phase 0 complete

### Objectives

Implement the AI Reasoner that decides whether to use cached patterns or VLM discovery.

### File Created

**`core/reasoner.py`**

### Key Responsibilities

- Accept task goal + context
- Query Qdrant for similar patterns
- If pattern found (confidence > 0.7): Return pattern-based plan
- If no pattern: Return discovery plan (use VLM)
- Generate execution strategy with fallback logic

### Implementation

```python
from typing import Optional, Dict, List
from core.memory.pattern_store import PatternStore
from dataclasses import dataclass

@dataclass
class ExecutionPlan:
    """Plan for executing a task."""
    plan_type: str  # "pattern" | "discovery"
    pattern_id: Optional[str]
    steps: List[Dict]
    estimated_vlm_calls: int
    confidence: float

class AIReasoner:
    """AI-based strategic planner for browser automation tasks."""

    def __init__(self, pattern_store: PatternStore, gemini_api_key: str):
        self.pattern_store = pattern_store
        self.gemini_api_key = gemini_api_key
        self.confidence_threshold = 0.7

    async def plan_task(self, goal: str, url: str, context: dict) -> ExecutionPlan:
        """Generate execution plan for task.

        Strategy:
        1. Query memory for similar patterns
        2. If high-confidence pattern exists (>0.7), use it
        3. Otherwise, create discovery plan with VLM
        """
        # 1. Query memory for similar patterns
        patterns = await self.pattern_store.query_similar(goal, url, limit=5)

        # 2. If high-confidence pattern exists, use it
        if patterns and patterns[0].confidence > self.confidence_threshold:
            logger.info("Found high-confidence pattern: %s (%.2f)",
                       patterns[0].id, patterns[0].confidence)
            return self._create_pattern_plan(patterns[0])

        # 3. Otherwise, create discovery plan
        logger.info("No pattern found, using VLM discovery mode")
        return await self._create_discovery_plan(goal, url, context)

    def _create_pattern_plan(self, pattern: Pattern) -> ExecutionPlan:
        """Create execution plan from cached pattern."""
        return ExecutionPlan(
            plan_type="pattern",
            pattern_id=pattern.id,
            steps=pattern.pattern_data["sequence"],
            estimated_vlm_calls=0,  # No VLM needed!
            confidence=pattern.confidence
        )

    async def _create_discovery_plan(self, goal: str, url: str, context: dict) -> ExecutionPlan:
        """Use Gemini to reason about task structure for unknown tasks."""
        # Use Gemini to analyze task requirements
        # Return plan with VLM-heavy exploration
        prompt = f"""Analyze this browser automation task:

        Goal: {goal}
        URL: {url}
        Context: {context}

        Create a step-by-step plan using: navigate, observe, click, fill, wait
        """

        # Call Gemini API (implementation details)
        # Parse response into steps

        return ExecutionPlan(
            plan_type="discovery",
            pattern_id=None,
            steps=parsed_steps,
            estimated_vlm_calls=len([s for s in parsed_steps if s["action"] == "observe"]),
            confidence=0.5  # Unknown task, medium confidence
        )
```

### Integration Point

**Modify `core/orchestrator.py`:**
```python
# Replace hardcoded _plan_task()
class Orchestrator:
    def __init__(self):
        self.reasoner = AIReasoner(pattern_store, gemini_api_key)

    async def _plan_task(self, task_id: str):
        task = self.db.get_task(task_id)

        # Use AI reasoner instead of hardcoded logic
        plan = await self.reasoner.plan_task(
            goal=task.goal,
            url=task.start_url,
            context=task.context
        )

        # Store plan for execution
        task.execution_plan = plan
        task.pattern_id = plan.pattern_id
        self.db.update_task(task_id, task)
```

### Testing

**Unit Tests (4 tests):**
- `test_reasoner_pattern_retrieval()` - Mock pattern store, verify retrieval
- `test_reasoner_fallback_discovery()` - Verify fallback when no pattern
- `test_reasoner_confidence_threshold()` - Verify 0.7 threshold behavior
- `test_reasoner_with_orchestrator()` - End-to-end with mock memory

### Success Criteria

- ✅ Reasoner can query Qdrant for patterns (mock for now)
- ✅ Returns pattern-based plans when confidence > 0.7
- ✅ Falls back to discovery when no pattern/low confidence
- ✅ Orchestrator uses reasoner instead of hardcoded planning
- ✅ All 4 unit tests pass

### PM Validation

```bash
# PM agent validates:
pytest tests/test_reasoner.py -v
python -c "from core.reasoner import AIReasoner; print('Import successful')"
```

---

## Phase 2: Qdrant Pattern Store & Embeddings

**Supervising Agent:** Database Specialist
**Estimated Time:** 2-3 hours
**Dependencies:** Phase 1 complete

### Objectives

1. Implement Qdrant embedded mode for vector storage
2. Implement embedding service using sentence-transformers
3. Create pattern store interface compatible with reasoner

### Files Created

- `core/memory/embeddings.py` - Embedding generation service
- `core/memory/pattern_store.py` - Qdrant interface

### Embedding Service Implementation

```python
from sentence_transformers import SentenceTransformer
from typing import List
from urllib.parse import urlparse

class EmbeddingService:
    """Generate embeddings for semantic search."""

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
        self._cache = {}  # In-memory cache

    async def generate(self, text: str) -> List[float]:
        """Generate 384-dim embedding for text."""
        # Check cache first
        if text in self._cache:
            return self._cache[text]

        # Generate embedding
        embedding = self.model.encode(text, convert_to_numpy=True)

        # Cache result
        self._cache[text] = embedding.tolist()

        return embedding.tolist()

    async def generate_task_embedding(self, url: str, goal: str) -> List[float]:
        """Generate embedding for task (URL domain + goal)."""
        domain = urlparse(url).netloc
        text = f"{domain} {goal}"
        return await self.generate(text)
```

### Qdrant Pattern Store Implementation

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter
from typing import List, Optional
import os

class PatternStore:
    """Interface for storing and retrieving patterns from Qdrant."""

    def __init__(self, storage_path: str = "./qdrant_storage"):
        # Embedded mode - no API key needed!
        self.client = QdrantClient(path=storage_path)
        self.collection_name = "spectacles-memory"
        self.embeddings = EmbeddingService()

        # Create collection if doesn't exist
        self._ensure_collection()

    def _ensure_collection(self):
        """Create Qdrant collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        if self.collection_name not in [c.name for c in collections]:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

    async def query_similar(self, goal: str, url: str, limit: int = 5) -> List[Pattern]:
        """Query Qdrant for similar patterns."""
        # 1. Generate embedding
        embedding = await self.embeddings.generate_task_embedding(url, goal)

        # 2. Query Qdrant
        domain = urlparse(url).netloc
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            limit=limit,
            query_filter=Filter(
                must=[{"key": "site_domain", "match": {"value": domain}}]
            )
        )

        # 3. Hydrate patterns from database
        patterns = []
        for result in results:
            pattern = await self._hydrate_pattern(result.id)
            if pattern:
                pattern.similarity_score = result.score
                patterns.append(pattern)

        return patterns

    async def store_pattern(self, pattern: Pattern):
        """Store pattern in Qdrant and SQLite."""
        # 1. Generate embedding
        embedding = await self.embeddings.generate_task_embedding(
            pattern.site_url,
            pattern.goal
        )

        # 2. Store in Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=pattern.id,
                    vector=embedding,
                    payload={
                        "site_domain": pattern.site_domain,
                        "pattern_type": pattern.pattern_type,
                        "created_at": pattern.created_at.isoformat(),
                        "last_used_at": pattern.last_used_at.isoformat()
                    }
                )
            ]
        )

        # 3. Store full data in SQLite
        db.insert("learned_patterns", pattern.to_dict())

    async def update_confidence(self, pattern_id: str, success: bool):
        """Update pattern confidence after use."""
        if success:
            db.increment("learned_patterns", pattern_id, "success_count")
        else:
            db.increment("learned_patterns", pattern_id, "failure_count")

        # Update last_used_at
        db.update("learned_patterns", pattern_id, {
            "last_used_at": datetime.utcnow()
        })

    async def _hydrate_pattern(self, pattern_id: str) -> Optional[Pattern]:
        """Fetch full pattern from SQLite."""
        row = db.get("learned_patterns", pattern_id)
        if not row:
            return None
        return Pattern.from_dict(row)
```

### Testing

**Unit Tests (6 tests):**
- `test_embeddings_generation()` - Verify shape (384-dim) and speed (<100ms)
- `test_embeddings_similarity()` - Similar tasks have cosine similarity > 0.75
- `test_embeddings_cache()` - Caching works correctly
- `test_pattern_store_upsert()` - Pattern storage in Qdrant
- `test_pattern_store_query()` - Pattern retrieval with filtering
- `test_pattern_store_confidence()` - Confidence updates in SQLite

**Integration Test:**
- `test_qdrant_integration()` - Full cycle: store → query → retrieve

### Success Criteria

- ✅ Qdrant collection created successfully
- ✅ Embeddings generated in < 100ms
- ✅ Similar tasks have cosine similarity > 0.75
- ✅ Patterns stored in Qdrant with metadata
- ✅ Patterns queryable via semantic search
- ✅ All 6 unit tests + integration test pass

### PM Validation

```bash
pytest tests/test_embeddings.py -v
pytest tests/test_pattern_store.py -v
python -c "from qdrant_client import QdrantClient; c = QdrantClient(path='./qdrant_storage'); print(c.get_collections())"
```

---

## Phase 3: Pattern Extraction Engine

**Supervising Agent:** Backend Architect
**Estimated Time:** 2-3 hours
**Dependencies:** Phase 2 complete

### Objectives

Extract patterns from successful task executions and classify them automatically.

### File Created

**`core/memory/extractor.py`**

### Pattern Classification Logic

```python
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urlparse

class PatternExtractor:
    """Extract patterns from successful task executions."""

    async def extract_from_task(self, task_id: str) -> Optional[Pattern]:
        """Extract pattern from completed task."""
        # 1. Get task and actions
        task = db.get_task(task_id)
        actions = db.get_task_actions(task_id)

        if not actions or task.status != "COMPLETED":
            return None

        # 2. Classify pattern type
        pattern_type = self._classify_pattern(actions)

        # 3. Extract selectors and sequence
        selectors = self._extract_selectors(actions)
        sequence = self._build_action_sequence(actions)

        # 4. Extract success indicators
        success_indicators = self._extract_success_signals(task, actions)

        # 5. Create pattern object
        return Pattern(
            id=generate_id(),
            site_domain=urlparse(task.start_url).netloc,
            site_url=task.start_url,
            goal=task.goal,
            pattern_type=pattern_type,
            pattern_data={
                "selectors": selectors,
                "sequence": sequence,
                "success_indicators": success_indicators
            },
            success_count=1,
            failure_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

    def _classify_pattern(self, actions: List[Action]) -> str:
        """Classify pattern type based on action sequence.

        Rules:
        - LOGIN_FLOW: Fill fields (email/username + password) + submit
        - FORM_STRUCTURE: Multiple fill actions + submit
        - NAVIGATION: Primarily click actions
        - EXTRACTION: Primarily observe actions
        """
        fills = sum(1 for a in actions if a.type == "fill")
        clicks = sum(1 for a in actions if a.type == "click")
        observes = sum(1 for a in actions if a.type == "observe")

        # Detect login patterns
        field_names = [a.metadata.get("field_name", "").lower()
                      for a in actions if a.type == "fill"]
        has_auth_fields = any(x in field_names for x in
                             ["email", "username", "password", "login"])

        if has_auth_fields and fills >= 2:
            return "LOGIN_FLOW"
        elif fills > clicks and fills > 2:
            return "FORM_STRUCTURE"
        elif clicks > fills:
            return "NAVIGATION"
        elif observes > (clicks + fills):
            return "EXTRACTION"
        else:
            return "GENERIC"

    def _extract_selectors(self, actions: List[Action]) -> Dict[str, str]:
        """Extract key selectors."""
        selectors = {}
        for action in actions:
            if action.selector:
                semantic_name = self._generate_semantic_name(action)
                selectors[semantic_name] = action.selector
        return selectors

    def _build_action_sequence(self, actions: List[Action]) -> List[Dict]:
        """Build ordered action sequence."""
        sequence = []
        for action in actions:
            step = {"action": action.type, "target": action.selector or action.text}
            if action.type == "fill":
                step["field"] = action.metadata.get("field_name")
            sequence.append(step)
        return sequence

    def _extract_success_signals(self, task: Task, actions: List[Action]) -> Dict:
        """Extract indicators that task succeeded."""
        signals = {}
        if task.final_url and task.final_url != task.start_url:
            signals["url_contains"] = urlparse(task.final_url).path
        return signals

    def _generate_semantic_name(self, action: Action) -> str:
        """Generate semantic name for selector."""
        if action.type == "fill":
            field_name = action.metadata.get("field_name", "field")
            return f"{field_name}_field"
        elif action.type == "click":
            text = (action.text or "button").lower().replace(" ", "_")
            return f"{text}_button"
        else:
            return f"{action.type}_{action.id[:8]}"
```

### Testing

**Unit Tests (6 tests):**
- `test_classification_login()` - LOGIN_FLOW detection (80%+ accuracy)
- `test_classification_form()` - FORM_STRUCTURE detection
- `test_classification_navigation()` - NAVIGATION detection
- `test_selector_extraction()` - Semantic naming
- `test_sequence_building()` - Action ordering preserved
- `test_success_signals()` - URL/text indicators

### Success Criteria

- ✅ Pattern classification accuracy > 80%
- ✅ Selectors extracted for all interactive actions
- ✅ Action sequences preserve order
- ✅ Success indicators detected
- ✅ All 6 unit tests pass

### PM Validation

```bash
pytest tests/test_extractor.py -v
# PM runs extraction on sample task data
```

---

## Phase 4: Learning Integration & Confidence Tracking

**Supervising Agent:** Backend Architect
**Estimated Time:** 1-2 hours
**Dependencies:** Phase 3 complete

### Objectives

Wire everything together - automatic pattern extraction on task completion and confidence tracking.

### Files Modified

- `core/orchestrator.py` - Add pattern extraction hook
- `core/browser_specialist.py` - Track selector usage

### Integration Hooks

```python
# In orchestrator.py
class Orchestrator:
    def __init__(self):
        self.reasoner = AIReasoner(pattern_store, gemini_key)
        self.pattern_extractor = PatternExtractor()
        self.pattern_store = PatternStore()

    async def execute_task(self, task_id: str):
        """Execute task with pattern learning."""
        # ... existing execution logic ...

        # AFTER successful completion:
        if task.status == "COMPLETED":
            try:
                # Extract pattern from successful execution
                pattern = await self.pattern_extractor.extract_from_task(task_id)

                if pattern:
                    # Store in Qdrant + SQLite
                    await self.pattern_store.store_pattern(pattern)

                    logger.info("Learned new pattern: %s for %s",
                               pattern.pattern_type, pattern.site_domain)
            except Exception as e:
                logger.error("Pattern extraction failed: %s", e)
                # Don't fail task if learning fails

        # If task used an existing pattern, update confidence
        if task.pattern_id:
            success = (task.status == "COMPLETED")
            await self.pattern_store.update_confidence(task.pattern_id, success)
```

### Confidence Calculation

```python
def calculate_confidence(pattern: Pattern) -> float:
    """Calculate pattern confidence (0.0-1.0).

    Factors:
    1. Success rate (primary)
    2. Sample size (confidence in rate)
    3. Recency (penalize stale patterns)
    """
    total = pattern.success_count + pattern.failure_count
    if total == 0:
        return 0.5

    # Base confidence
    base_confidence = pattern.success_count / total

    # Sample size adjustment
    if total < 10:
        sample_penalty = 0.1 * (1 - total / 10)
        base_confidence -= sample_penalty

    # Staleness penalty (30+ days)
    days_since_use = (datetime.utcnow() - pattern.last_used_at).days
    if days_since_use > 30:
        staleness_penalty = min(0.3, 0.01 * (days_since_use - 30))
        base_confidence -= staleness_penalty

    return max(0.0, min(1.0, base_confidence))
```

### Testing

**Unit Tests (4 tests):**
- `test_orchestrator_extraction_hook()` - Extraction called on success
- `test_confidence_calculation()` - Formula correctness
- `test_confidence_sample_size()` - Sample penalty works
- `test_confidence_staleness()` - Staleness penalty works

**Integration Tests (3 tests):**
- `test_full_learning_cycle()` - Task A creates pattern, Task B uses it
- `test_confidence_update_success()` - Confidence increases
- `test_confidence_update_failure()` - Confidence decreases

### Success Criteria

- ✅ Patterns auto-extracted from successful tasks
- ✅ Pattern confidence updated after each use
- ✅ Confidence formula works (high success = high confidence)
- ✅ Stale patterns penalized
- ✅ All 7 tests pass

### PM Validation

```bash
pytest tests/test_integration.py -v
pytest tests/ -v  # Full suite
```

---

## Scope Boundaries

### In Scope
- ✅ Project rename (spectacles → spectacles)
- ✅ GCP secret migration
- ✅ Qdrant embedded mode (fully isolated)
- ✅ AI reasoner for strategic planning
- ✅ Memory query before task execution
- ✅ Pattern extraction from successful tasks
- ✅ Confidence tracking
- ✅ Orchestrator integration
- ✅ Gemini-based reasoning

### Out of Scope (Future Phases)
- ❌ Pattern versioning (when sites change)
- ❌ Multi-site pattern generalization
- ❌ Pattern conflict resolution
- ❌ Advanced learning (reinforcement learning)
- ❌ Pattern sharing across instances
- ❌ UI for pattern management
- ❌ Pattern pruning/cleanup
- ❌ Cloud Run deployment (local dev only)

### Auto-Fix Authority (No Approval)

PM and supervising agents CAN fix autonomously:
- ✅ Bug fixes in pattern matching
- ✅ Performance optimizations
- ✅ Error handling improvements
- ✅ Logging enhancements
- ✅ Confidence calculation tuning
- ✅ Test fixes

### Escalation Required

PM MUST escalate to user:
- ❌ New database tables
- ❌ Qdrant configuration changes
- ❌ New external dependencies (beyond plan)
- ❌ Breaking API changes
- ❌ Major architectural deviations
- ❌ Unresolvable blockers (after 3 attempts)

---

## Testing Strategy

### Unit Tests (25+ tests)

**Phase 0:**
- Verification scripts (not unit tests)

**Phase 1 (4 tests):**
- `test_reasoner.py` - Pattern retrieval, confidence threshold, fallback

**Phase 2 (6 tests):**
- `test_embeddings.py` - Generation, similarity, caching
- `test_pattern_store.py` - Upsert, query, confidence updates

**Phase 3 (6 tests):**
- `test_extractor.py` - Classification, selectors, sequences, signals

**Phase 4 (4 tests):**
- `test_orchestrator.py` - Extraction hook
- `test_confidence.py` - Calculation, penalties

### Integration Tests (6+ tests)

- `test_full_learning_cycle.py` - Extract → store → retrieve → execute
- `test_pattern_execution.py` - Pattern-based execution
- `test_discovery_execution.py` - VLM discovery mode
- `test_confidence_lifecycle.py` - Updates over multiple uses
- `test_qdrant_integration.py` - Real Qdrant operations
- `test_memory_flow.py` - End-to-end system

### PM Final Validation

```bash
# PM runs full test suite
pytest tests/ -v --tb=short

# Success criteria: 90%+ pass rate
# Failures analyzed, critical ones block completion
```

---

## Success Criteria

### Functional Requirements
- ✅ Project renamed to "spectacles" everywhere
- ✅ All GCP secrets migrated
- ✅ Qdrant embedded mode working
- ✅ Spectacles checks memory before every task
- ✅ Known patterns execute without VLM (0 VLM calls)
- ✅ Unknown tasks fall back to VLM discovery
- ✅ Successful tasks auto-store patterns
- ✅ Pattern confidence updates after each use
- ✅ Failed patterns trigger VLM fallback

### Performance Targets
- ✅ **Pattern-based execution:** 3-5 seconds (vs 20-30s)
- ✅ **Cost reduction:** $0.00-0.01 per task (vs $0.05-0.08)
- ✅ **Memory query latency:** < 500ms
- ✅ **Pattern extraction:** < 1 second
- ✅ **Embedding generation:** < 100ms

### Data Quality
- ✅ 90%+ pattern recall (retrieves relevant patterns)
- ✅ 80%+ pattern precision (retrieved patterns useful)
- ✅ Confidence scores correlate with success rate
- ✅ Pattern classification accuracy > 80%

### Infrastructure
- ✅ Docker image builds successfully (< 3GB)
- ✅ Cold start time < 6 seconds
- ✅ Qdrant storage persists correctly
- ✅ No shared resources (complete isolation)

---

## Rollout Plan

### Phase 0-4: Development (This Plan)
**Total Estimated Time:** 10-14 hours (5-6 sessions)

| Phase | Agent | Time | Cumulative |
|-------|-------|------|------------|
| Phase 0 | Refactor Specialist | 0.5-1 hr | 0.5-1 hr |
| Phase 1 | AI Integration | 2-3 hr | 2.5-4 hr |
| Phase 2 | Database Specialist | 2-3 hr | 4.5-7 hr |
| Phase 3 | Backend Architect | 2-3 hr | 6.5-10 hr |
| Phase 4 | Backend Architect | 1-2 hr | 7.5-12 hr |
| Testing | PM Agent | 1-2 hr | 8.5-14 hr |
| Final Validation | PM Agent | 1 hr | 9.5-15 hr |

### Post-Development

**Staging Validation (Manual):**
1. Deploy to staging environment
2. Monitor pattern learning over 50+ tasks
3. Verify cost/performance improvements
4. Review pattern quality

**Production Rollout (Future):**
1. Deploy behind feature flag
2. Enable for 10% of tasks
3. Monitor for regressions
4. Gradual rollout to 100%

---

## Dependencies

### External Services
- ✅ **Google AI API** - `spectacles-google-ai-api-key` (dedicated, isolated)
- ✅ **Qdrant** - Embedded mode (no external service)
- ✅ **sentence-transformers** - Local model (packaged in Docker)

### Internal Components
- ✅ Orchestrator (modified)
- ✅ BrowserSpecialist (track selectors)
- ✅ Database (SQLite with `learned_patterns` table)

### New Dependencies

**requirements.txt additions:**
```txt
# Remove:
# pinecone-client>=6.0.0

# Add:
qdrant-client==1.7.0
sentence-transformers==2.3.1
```

### Environment Variables

```bash
# Updated .env
GOOGLE_AI_API_KEY=<from spectacles-google-ai-api-key>
VLM_MODEL=gemini-2.0-flash-exp

# Qdrant (embedded mode)
QDRANT_STORAGE_PATH=./qdrant_storage
QDRANT_COLLECTION=spectacles-memory

# Pattern Learning
MEMORY_ENABLED=true
PATTERN_CONFIDENCE_THRESHOLD=0.7

# Database
DB_PATH=./spectacles.db
```

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|-----------|
| Rename breaks imports | High | Low | Automated testing after rename |
| GCP secret access issues | Medium | Low | Validate before proceeding |
| Qdrant storage issues | Medium | Low | Persistent volume configuration |
| Pattern extraction bugs | Medium | Medium | 80%+ accuracy target, extensive tests |
| Embeddings quality poor | High | Low | Pre-validation script |
| Docker image too large | Low | Medium | Multi-stage build, < 3GB acceptable |
| Cold start delays | Medium | Medium | Model caching, < 6s acceptable |
| PM agent blockers | Medium | Low | Escalation protocol after 3 attempts |

**Overall Risk:** Low-Medium (mitigated by automated testing and PM validation)

---

## Docker Configuration

### Multi-Stage Dockerfile

```dockerfile
# Stage 1: Download models
FROM python:3.12-slim as model-stage

RUN pip install --no-cache-dir sentence-transformers
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Stage 2: Production
FROM python:3.12-slim

# Copy model cache
COPY --from=model-stage /root/.cache/torch /root/.cache/torch

# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create Qdrant storage directory
RUN mkdir -p ./qdrant_storage

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Image Size:** ~2.3GB (acceptable for Cloud Run)
**Cold Start:** 4-6s (acceptable)

---

## Execution Instructions

### For User (You)

**Execute this plan with:**
```bash
/gsd:execute-plan projects/spectacles/.planning/phases/01-reasoning-engine/PLAN.md
```

**What happens:**
1. PM agent spawns (project-manager)
2. PM validates environment and prerequisites
3. PM spawns Phase 0 agent (refactor-specialist)
4. Phase 0 completes → PM validates → Phase 1
5. Phase 1 completes → PM validates → Phase 2
6. ... continues autonomously through Phase 4
7. PM runs full test suite
8. PM creates SUMMARY.md
9. PM reports completion to you

**Zero user input required.** PM handles everything autonomously.

---

## PM Agent Prompt Template

```
You are the Project Manager agent for the Spectacles AI Reasoning Engine implementation.

Your responsibilities:
1. Execute Phases 0-4 sequentially by spawning supervising agents
2. Validate phase completion via automated tests before proceeding
3. Handle blockers (up to 3 resolution attempts, then escalate)
4. Make autonomous decisions within plan scope
5. Create comprehensive SUMMARY.md at completion

Plan location: projects/spectacles/.planning/phases/01-reasoning-engine/PLAN.md

Authority:
- CAN: Architecture details, code structure, optimizations, auto-fixes
- MUST ESCALATE: Schema changes, breaking changes, new dependencies, unresolvable blockers

Success criteria: All phases complete, 90%+ tests pass, SUMMARY created.

Begin with Phase 0.
```

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-01-19 | Initial plan |
| v1.1 | 2026-01-20 | Task restructuring, Pinecone config, validation |
| v2 | 2026-01-20 | **Major revision:**<br>- Added Phase 0 (rename)<br>- PM orchestration structure<br>- Switched Pinecone → Qdrant<br>- Isolated resources<br>- Autonomous execution |

---

**Plan Created:** 2026-01-19
**Plan Revised:** 2026-01-20 (v2)
**Author:** Claude (GSD Planning Mode)
**Status:** Ready for Autonomous Execution
**Execution Method:** `/gsd:execute-plan projects/spectacles/.planning/phases/01-reasoning-engine/PLAN.md`

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
