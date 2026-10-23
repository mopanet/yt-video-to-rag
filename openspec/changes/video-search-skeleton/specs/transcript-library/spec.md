# Spec Delta

## Purpose

Keeps every ingested video as citable, timestamped passages in one local library shared by all
channels, so that search always points back to the exact moment of the exact video and the
library stays consistent across repeated and interrupted ingests.

## ADDED Requirements

### Requirement: Library location
The library SHALL be a single file in the operating system's per-user data directory for
`video-to-rag`. The environment variable `VIDEO_TO_RAG_HOME` SHALL override the directory, and the
`--data-dir` option SHALL override both. The file SHALL be created on the first successful ingest.

#### Scenario: Default location
- **WHEN** neither `--data-dir` nor `VIDEO_TO_RAG_HOME` is given and a video is ingested on Linux
- **THEN** the library is created under `~/.local/share/video-to-rag/`

#### Scenario: Environment override
- **WHEN** `VIDEO_TO_RAG_HOME=/srv/vtr` is set and a video is ingested
- **THEN** the library is created under `/srv/vtr/`

#### Scenario: Option beats environment
- **WHEN** `VIDEO_TO_RAG_HOME=/srv/vtr` is set and the user passes `--data-dir /tmp/lib`
- **THEN** the library under `/tmp/lib/` is used and `/srv/vtr/` is not touched

### Requirement: Timestamped passages
Each transcript SHALL be stored as passages of consecutive segments, in order. A passage's start
and end SHALL be the start of its first and the end of its last segment, and its text the segments'
text verbatim. Consecutive passages SHALL overlap by at least one segment so that no sentence is
only ever seen cut in half.

#### Scenario: Whole transcript covered in order
- **WHEN** a transcript is stored
- **THEN** every segment's text appears in at least one passage, and passages ordered by start time follow the transcript order

#### Scenario: Passage boundaries are segment boundaries
- **WHEN** a passage is formed from segments starting at 600.0 s and ending at 671.4 s
- **THEN** the passage's start is 600.0 s and its end is 671.4 s

#### Scenario: Neighbouring passages overlap
- **WHEN** a transcript yields more than one passage
- **THEN** each passage's last segment also appears at the beginning of the next passage

### Requirement: Passage size bound
A passage SHALL never exceed the input limit of the embedding model, so that no text is silently
cut off before it is embedded. A single segment longer than the limit SHALL be split into parts at
word boundaries, each part keeping the segment's start and end times.

#### Scenario: Oversized segment
- **WHEN** a caption segment holds more words than fit the model's input limit
- **THEN** it is stored as several passages, none over the limit, and every word of the segment is stored

### Requirement: Shared multi-channel library
Videos from any number of channels SHALL be stored in the same library, each attributed to its
channel id and channel name.

#### Scenario: Two channels side by side
- **WHEN** one video of channel A and one video of channel B are ingested
- **THEN** both videos are searchable from the same library and each hit names its own channel

### Requirement: Idempotent and atomic ingest
Ingesting a video that is already in the library SHALL replace its metadata and passages instead
of adding duplicates. An ingest that fails or is interrupted SHALL leave the library as it was
before that ingest started.

#### Scenario: Same video twice
- **WHEN** the same video is ingested twice
- **THEN** the library holds that video's passages once, and a search returns each of them at most once

#### Scenario: Interrupted re-ingest
- **WHEN** a re-ingest of an already stored video is interrupted before it finishes
- **THEN** the previously stored passages of that video are still stored and searchable

### Requirement: Embedding model bookkeeping
The library SHALL record which embedding model built it. When this version of the tool uses a
different embedding model than the one recorded, ingest and search SHALL refuse with a message
naming both models, and the library SHALL be unchanged.

#### Scenario: Model mismatch
- **WHEN** the library was built with model X and the tool now uses model Y
- **THEN** ingest and search exit non-zero with a message naming X and Y, and the library is unchanged

### Requirement: Ingest summary
A successful ingest SHALL report the video title, channel name, number of passages stored, the
caption kind (`manual` or `auto`), the caption language, and the library path.

#### Scenario: Summary after success
- **WHEN** a 2-hour English video with automatic captions is ingested
- **THEN** the output names its title and channel, the number of passages, `auto`, `en`, and the library path
