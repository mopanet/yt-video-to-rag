# Spec Delta

## Purpose

Finds the passages that answer a question asked in any language, across videos spoken in any
language, and returns each one with everything needed to cite it: the video, the exact moment and
the original words.

## ADDED Requirements

### Requirement: Cross-language retrieval
Search SHALL rank passages by meaning independently of language, so that a query in one language
finds a passage that answers it in another language.

#### Scenario: Hungarian question, English passages
- **WHEN** the library holds English passages on focus, caffeine, cold exposure, sleep and exercise, and the query is "Hogyan tudom javítani a fókuszomat munka közben?"
- **THEN** the passage about improving focus is the first hit

### Requirement: Exact-term matching
Search SHALL also match the query's words literally, so that a passage containing a rare term or
name from the query ranks among the top hits even when its meaning-based score is weak.

#### Scenario: Rare term
- **WHEN** exactly one passage in the library contains the term "NSDR" and the query is "NSDR protocol"
- **THEN** that passage is among the first three hits

### Requirement: Several phrasings of one question
A search SHALL accept one to five non-blank queries (typically the question in the user's language
and its translation into the videos' language) and return one ranked list in which each passage
appears at most once.

#### Scenario: Two phrasings fused
- **WHEN** a search is made with the queries "hogyan javítsam a fókuszomat" and "how to improve focus"
- **THEN** one ranked list is returned and no passage appears in it twice

#### Scenario: Too many or blank queries
- **WHEN** a search is made with six queries, or with a query that is empty or only whitespace
- **THEN** the search is rejected with a message stating the one-to-five non-blank rule

### Requirement: Channel filter
A search SHALL optionally be limited to one channel, matched case-insensitively against the
channel name or exactly against the channel id. When no ingested channel matches, the search SHALL
return no hits and a message saying that no ingested channel matches.

#### Scenario: Filter by name
- **WHEN** the library holds videos of "Huberman Lab" and another channel, and the search is limited to "huberman lab"
- **THEN** every hit is from Huberman Lab

#### Scenario: Unknown channel
- **WHEN** the search is limited to a channel name that matches no ingested channel
- **THEN** no hits are returned and the message says no ingested channel matches that name

### Requirement: Result limit
A search SHALL return at most 8 hits by default. A caller SHALL be able to ask for between 1 and
20 hits; a larger request SHALL be capped at 20.

#### Scenario: Default and cap
- **WHEN** a search is made without a limit, and again with a limit of 50, on a library of 1000 passages
- **THEN** the first returns 8 hits and the second returns 20 hits

### Requirement: Search hit content
Every hit SHALL carry: video title, channel name, publish date (`YYYY-MM-DD`), start and end time
(`m:ss`, or `h:mm:ss` from one hour), a link `https://youtu.be/<video-id>?t=<start in whole
seconds>`, the passage text verbatim in its original language, and that language's code.

#### Scenario: Timestamped link
- **WHEN** a hit's passage starts at 1834.6 s and ends at 1912.0 s in video `abc123DEF45`
- **THEN** its link is `https://youtu.be/abc123DEF45?t=1834` and its time range reads `30:34`–`31:52`

#### Scenario: Original text kept
- **WHEN** an English passage is found by a Hungarian query
- **THEN** the hit's text is the English passage verbatim and its language is `en`

### Requirement: Empty library
When the library does not exist yet or holds no videos, a search SHALL return no hits and a
message saying the library is empty and that `video-to-rag ingest <video-url>` fills it. It SHALL
NOT create the library.

#### Scenario: Search before any ingest
- **WHEN** the user runs `video-to-rag search "focus"` before ever ingesting
- **THEN** the command prints that the library is empty with the ingest hint, exits zero, and no library file is created

### Requirement: Search command
`video-to-rag search <query> [<query>...] [--channel <name-or-id>] [--limit <n>]` SHALL print the
hits as a numbered list, each with title, channel, date, time range, link and passage text.

#### Scenario: Command-line search
- **WHEN** the user runs `video-to-rag search "how to improve focus" --limit 3` on a filled library
- **THEN** three numbered hits are printed, each with title, channel, date, time range, link and text
