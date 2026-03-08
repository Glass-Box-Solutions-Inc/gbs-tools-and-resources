# spectacles - Roadmap

**Last Updated:** 2026-01-19
**Status:** Active Planning

---

## Vision

**Transform Spectacles from a perception-driven automation tool into an intelligent learning agent.**

Spectacles will become smarter with every task by:
- Learning site-specific patterns automatically
- Retrieving proven approaches from memory
- Reducing VLM API costs by 80%+ for repeated tasks
- Executing 5-10x faster on known sites

---

## Phases

### Phase 1: AI Reasoning Engine & Memory Intelligence Layer
**Status:** Planning
**Target:** Q1 2026
**Plan:** [01-reasoning-engine/PLAN.md](phases/01-reasoning-engine/PLAN.md)

**Objective:** Add strategic planning and pattern learning capabilities

**Key Deliverables:**
1. AI Reasoner - LLM-based strategic task planner
2. Memory Query System - Semantic pattern retrieval from Pinecone
3. Pattern Extraction - Automatic learning from successful tasks
4. Confidence System - Track and adapt based on success/failure rates

**Success Metrics:**
- Pattern-based tasks execute in 3-5 seconds (vs 20-30s baseline)
- Cost reduced to $0.00-0.01 per task (vs $0.05-0.08 baseline)
- 90%+ pattern recall for known sites
- Patterns stored and retrieved successfully

**Dependencies:**
- Pinecone API (configured, needs implementation)
- Gemini 2.0 Flash (already integrated)
- sentence-transformers library (new dependency)

---

### Phase 2: Pattern Intelligence (Future)
**Status:** Not Started
**Target:** Q2 2026

**Planned Features:**
- Pattern versioning (detect site changes)
- Multi-site pattern generalization
- Pattern conflict resolution
- Advanced learning algorithms
- Pattern sharing across instances

---

### Phase 3: Desktop Automation Enhancement (Future)
**Status:** Not Started
**Target:** Q2-Q3 2026

**Planned Features:**
- Full PyAutoGUI integration
- OCR-based text extraction
- Window management automation
- Mixed web + desktop workflows

---

## Success Metrics

### Phase 1 Targets
- [x] Pinecone infrastructure configured
- [x] Database schema for learned_patterns created
- [ ] AI Reasoner implemented and integrated
- [ ] Memory query system functional
- [ ] Pattern extraction working on successful tasks
- [ ] 50+ patterns learned and stored
- [ ] 80%+ cost reduction on repeated tasks
- [ ] 5x speed improvement on known sites

### Overall Project Health
- [ ] Production uptime > 99%
- [ ] Average task completion rate > 85%
- [ ] HITL approval rate < 30% (most tasks auto-complete)
- [ ] VLM budget < $50/month (with memory optimization)

---

## Dependencies

### External Services
- ✅ Browserless.io (production account)
- ✅ Google AI / Gemini 2.0 Flash API
- ✅ Pinecone vector database
- ✅ GCP Secret Manager
- ✅ Slack API (webhooks + Socket Mode)

### Internal Components
- ✅ Core automation (orchestrator + browser specialist)
- ✅ Perception layer (DOM + VLM hybrid)
- ✅ State machine & checkpoints
- ⏳ AI Reasoner (Phase 1)
- ⏳ Memory system (Phase 1)
- ⏳ Pattern extraction (Phase 1)

---

## Risk Mitigation

| Risk | Phase | Mitigation |
|------|-------|-----------|
| Pinecone costs escalate | 1 | Implement caching, monitor usage, set budget alerts |
| Bad patterns stored | 1 | Confidence thresholds, manual review capability |
| Pattern extraction bugs | 1 | Extensive testing, staged rollout |
| Site changes break patterns | 2 | Pattern versioning, confidence decay over time |
| Memory queries too slow | 1 | Index optimization, response caching |

---

## Timeline

```
Q1 2026 (Jan-Mar)
├─ Jan: Phase 1 Planning & Design
├─ Feb: Phase 1 Implementation
└─ Mar: Phase 1 Testing & Rollout

Q2 2026 (Apr-Jun)
├─ Apr: Phase 1 Production Stabilization
├─ May: Phase 2 Planning
└─ Jun: Phase 2 Implementation Start

Q3 2026 (Jul-Sep)
└─ Phase 2 Completion & Phase 3 Planning
```

---

## Long-Term Vision (2027+)

- **Adaptive Intelligence:** Spectacles learns from every interaction
- **Cross-Project Patterns:** Share learned patterns across all GBS projects
- **Predictive Automation:** Anticipate user needs based on patterns
- **Zero-VLM Mode:** 95%+ of tasks execute without vision AI calls
- **Self-Healing:** Automatically detect and adapt to site changes

---

*Last updated: 2026-01-19 by Claude (GSD Planning)*

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
