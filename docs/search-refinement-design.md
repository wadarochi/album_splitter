# Search Refinement Design

## Problem Statement
Short or ambiguous album titles (e.g., S.H.E "Play", "Together", "Encore") consistently return irrelevant results across metadata sources.

## Research Findings

### beets Pattern (Preferred)
- Interactive loop: choose_candidate() -> prompt -> manual_search() / manual_id() -> new Proposal -> loop continues
- Prompt options: [A]pply, [M]ore candidates, [S]kip, [U]se as-is, [E]nter search, [I]nter Id, [eDit], [aBort]
- Key insight: Loop continues with updated candidates; user can refine multiple times

### MusicBrainz Picard Pattern
- Three-tier matching: Tier 1 (barcode, catno, ISRC) -> Tier 2 (title, artist, length, tracks, date) -> Tier 3 (type, country, format)
- Key insight: Disambiguation signals are explicitly weighted; identifiers > similarity > preferences

### whipper Pattern
- Multiple releases: Duration-delta auto-select + --prompt for interactive choice + --release-id for pre-selection
- Key insight: Show all disambiguation signals in the prompt; let user choose based on metadata

## Proposed Solution

### 1. Enhanced Interactive Loop
Extend interactive.py with two new prompt options:
- [E]nter search: Prompt for new query, re-run search, continue loop
- [I]nter Id: Prompt for source:id (e.g., netease:12345), fetch directly, continue loop

### 2. Disambiguation Signal Enhancement
Extend AlbumScore with new signal fields:
- year_match: Query year matches album date
- barcode_match: Barcode in query matches
- catalog_match: Catalog number in query matches
- track_name_similarity: Jaccard similarity of track titles
- country_hint: Country from source (e.g., "TW", "CN")
- disambiguation: Source disambiguation comment

### 3. Progressive Search Strategy
Implement search_album_progressive() with three tiers:
- Tier 1: Exact ID Lookup (barcode/ISRC/catalog/source:id)
- Tier 2: Text Search with Signal Extraction
- Tier 3: Ambiguous Result with Suggestions

### 4. Query Suggestion Engine
Implement generate_refinement_suggestions() based on signal divergence.

## Implementation Phases
1. Core Loop Changes (interactive.py)
2. Signal Enhancement (rank.py)
3. Progressive Search (search.py)
4. Testing

## Files to Modify
- cue_finder/core/interactive.py
- cue_finder/core/rank.py
- cue_finder/core/search.py
- tests/test_interactive.py
- tests/test_rank.py
- docs/metadata-search.md
- openspec/specs/metadata-search/spec.md
