# Research protocol

How to conduct targeted research for technical design documents. Read
this before Phase 1 (Research).

## Purpose of research in a design document

Research serves the design, not the other way around. Every piece of
research must connect to a design decision. If a finding does not
inform a choice, it does not belong in the document.

Research answers three questions:

1. **What exists?** Tools, libraries, frameworks, protocols, and
   standards that occupy the design space.
2. **What works?** Benchmarks, case studies, and operational experience
   that indicate which approaches succeed and which fail.
3. **What constrains?** Specifications, compatibility requirements, and
   ecosystem realities that limit the design space.

## Firecrawl MCP usage

## Firecrawl MCP usage

A companion Firecrawl skill provides the complete tool surface, query
patterns, and usage guidance. Load it for the research phase. What
follows here is the research-specific decision framework — not the
tool mechanics.

### When to use Firecrawl

- **Documentation sites.** Crawl official docs for a framework,
  protocol, or tool to extract current API surfaces, configuration
  options, and architectural guidance.
- **GitHub repositories.** Scrape README files, specification
  documents, and CHANGELOG entries for competing or related projects.
- **Technical blogs and release notes.** Extract structured content
  from posts announcing new features, benchmarks, or architectural
  changes.
- **Specification documents.** Crawl RFC or W3C spec pages that
  `web_fetch` may render incompletely.

### When not to use Firecrawl

- **General knowledge questions.** If the answer is in training data
  and unlikely to have changed, do not burn a crawl on it.
- **Paywalled or authenticated content.** Firecrawl cannot bypass
  authentication.
- **Broad surveys.** Firecrawl is a scalpel, not a trawl net. Use
  `web_search` to identify targets, then Firecrawl to extract from
  specific pages.

### Dealing with Firecrawl unavailability

If Firecrawl MCP is not connected:

1. Use `web_search` to identify relevant pages.
2. Use `web_fetch` to extract content from specific URLs.
3. Note in the research summary that Firecrawl was unavailable and
   results may be less comprehensive for JavaScript-rendered or
   deeply-nested documentation.

Do not ask the user to connect Firecrawl unless the research genuinely
cannot proceed without it. Degrade gracefully.

## Source evaluation

Not all sources are equal. Apply these criteria:

### Tier 1 — Authoritative

- Official documentation and specification documents
- Peer-reviewed papers and published research
- Official project repositories (README, CHANGELOG, source code)
- RFCs and W3C specifications

Use freely. Cite with URL.

### Tier 2 — Informed

- Technical blog posts by project maintainers or known domain experts
- Conference talks with published slides or transcripts
- Well-maintained community wikis with citations

Use with attribution. Note the author's relationship to the project.

### Tier 3 — Contextual

- General technology journalism and aggregator sites
- Stack Overflow answers and forum discussions
- Tutorial sites and "awesome" lists

Use for ecosystem context and to identify what to investigate further.
Do not cite as authoritative for design decisions.

### Tier 4 — Avoid

- Marketing copy and vendor press releases (treat claims as
  unverified)
- AI-generated summaries on content farms
- Undated or unattributed blog posts

Do not cite. If information from these sources seems important,
corroborate it from a higher-tier source.

## Research summary format

Produce a working note (not part of the final document) structured as:

```markdown
## Research summary

### Ecosystem survey

| Tool/Project | Version | Relevance | Key findings | Source |
|---|---|---|---|---|
| ... | ... | ... | ... | URL |

### Standards and specifications

- [Spec name](URL): relevance to this design

### Key findings

1. Finding with source citation
2. Finding with source citation

### Research gaps

- Topics where authoritative sources could not be found
- Topics where sources conflict
```

This summary feeds Phase 2 (Outline) and Phase 4 (Drafting). It is a
working document, not a deliverable.

## Ecosystem survey depth

The ecosystem survey should be thorough enough to answer:

- "Why not use X instead?" for every plausible alternative
- "How does X handle this problem?" for every design challenge with
  known solutions
- "What version of X is current?" for every technology dependency

It should not attempt to be exhaustive. The goal is informed design
decisions, not a market landscape report.
