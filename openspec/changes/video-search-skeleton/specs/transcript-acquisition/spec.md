# Spec Delta

## Purpose

Turns a YouTube video into a timestamped transcript in the language actually spoken, together
with the metadata needed to cite it, under whatever network conditions the user is in (home
connection, browser cookies, or a proxy) without ever leaking the user's credentials.

## ADDED Requirements

### Requirement: Single video URL input
`video-to-rag ingest <url>` SHALL accept a single YouTube video URL in the `watch?v=`,
`youtu.be/`, `shorts/` and `live/` forms. Extra query parameters SHALL be ignored, and a playlist
parameter SHALL NOT expand the request to the playlist. Channel and playlist URLs SHALL be rejected
in this version with a message saying that channel ingest is not available yet.

#### Scenario: Watch URL with extra parameters
- **WHEN** the user runs `video-to-rag ingest "https://www.youtube.com/watch?v=abc123DEF45&t=90s&list=PL123"`
- **THEN** only video `abc123DEF45` is ingested and no other video of the playlist is touched

#### Scenario: Short link
- **WHEN** the user runs `video-to-rag ingest https://youtu.be/abc123DEF45`
- **THEN** the same video `abc123DEF45` is ingested

#### Scenario: Channel URL is not supported yet
- **WHEN** the user runs `video-to-rag ingest https://www.youtube.com/@hubermanlab`
- **THEN** the command exits non-zero with a message that channel ingest is not available yet, and the library is unchanged

#### Scenario: Not a YouTube URL
- **WHEN** the user runs `video-to-rag ingest https://example.com/video`
- **THEN** the command exits non-zero with a usage error and makes no network request

### Requirement: Video metadata
Ingest SHALL capture, for the video, its id, title, channel id, channel name, publish date,
duration and spoken language, so that every search hit can be cited without another request.

#### Scenario: Metadata available after ingest
- **WHEN** a video has been ingested
- **THEN** its title, channel name and publish date appear on every search hit that comes from it

### Requirement: Caption track selection
Ingest SHALL use captions in the video's spoken language only: an uploader-provided track first,
otherwise the automatically generated (speech recognition) track. Machine-translated tracks and
tracks in other languages SHALL NOT be used. When the metadata does not state the spoken language,
the language of the speech-recognition track SHALL be taken as the spoken language.

#### Scenario: Manual track preferred
- **WHEN** an English video has both an uploader-provided English track and an automatic English track
- **THEN** the uploader-provided track is used and recorded as `manual`

#### Scenario: Automatic track as fallback
- **WHEN** an English video has only an automatic English track (plus its machine translations)
- **THEN** the automatic English track is used and recorded as `auto`, and no translated track is used

#### Scenario: Spoken language missing from metadata
- **WHEN** the metadata states no language and the speech-recognition track is German
- **THEN** German is recorded as the spoken language and the German track is used

### Requirement: No usable captions
When the video has no caption track in its spoken language, ingest SHALL exit non-zero with a
message saying the video has no captions and that speech-to-text is not available yet, and SHALL
leave the library unchanged.

#### Scenario: Video without captions
- **WHEN** the user ingests a video that has no caption track in its spoken language
- **THEN** the command exits non-zero, says the video has no captions, and the library is unchanged

### Requirement: Timestamped transcript segments
The transcript SHALL be a sequence of segments, each with a start time and end time in seconds
and its text. Non-speech annotations in square brackets (such as `[Music]` or `[Applause]`) SHALL
be removed, and segments left empty SHALL be dropped.

#### Scenario: Non-speech annotations removed
- **WHEN** the captions contain a segment `[Music]` and a segment `[Applause] so let's begin`
- **THEN** the first segment is dropped and the second becomes `so let's begin` with its original timing

### Requirement: Network access modes
Ingest SHALL connect directly by default. `--cookies-from-browser <browser>[:<profile>]` SHALL send
that browser profile's YouTube cookies; `--cookies <file>` SHALL send the cookies from a
Netscape-format cookie file; the two flags SHALL be mutually exclusive. When the environment
variable `VIDEO_TO_RAG_PROXY` is set, every YouTube request SHALL go through that proxy.

#### Scenario: Browser cookies
- **WHEN** the user runs ingest with `--cookies-from-browser firefox`
- **THEN** the YouTube requests carry the cookies of the default Firefox profile

#### Scenario: Proxy from the environment
- **WHEN** `VIDEO_TO_RAG_PROXY=http://proxy.example:8080` is set and the user runs ingest
- **THEN** every YouTube request of that run goes through `proxy.example:8080`

#### Scenario: Conflicting cookie options
- **WHEN** the user passes both `--cookies-from-browser firefox` and `--cookies cookies.txt`
- **THEN** the command exits non-zero with a usage error before any network request

### Requirement: Credentials are never stored or shown
Cookie values, cookie file contents and proxy credentials SHALL NOT be written to the library,
to logs, or to standard output or error. A proxy URL that appears in any message SHALL have its
user and password masked. The proxy SHALL be configurable only through the environment, never as
a command-line argument.

#### Scenario: Proxy failure message is masked
- **WHEN** `VIDEO_TO_RAG_PROXY=http://alice:s3cret@proxy.example:8080` is set and the proxy refuses the connection
- **THEN** the error message shows `http://***@proxy.example:8080` and does not contain `alice` or `s3cret`

#### Scenario: No cookies in the library
- **WHEN** a video is ingested with `--cookies-from-browser firefox`
- **THEN** the library file contains no cookie names or values

### Requirement: Actionable block error
When YouTube refuses the request with its bot check ("Sign in to confirm you're not a bot"),
ingest SHALL exit non-zero with a message that explains the request was blocked, that this
typically happens from cloud or VPN addresses, and that names `--cookies-from-browser`,
`--cookies` and `VIDEO_TO_RAG_PROXY` as remedies. The library SHALL be unchanged.

#### Scenario: Blocked on a direct connection
- **WHEN** the user ingests a video directly and YouTube answers with the bot check
- **THEN** the command exits non-zero, explains the block, names the cookie options and `VIDEO_TO_RAG_PROXY`, and the library is unchanged

#### Scenario: Blocked although cookies were sent
- **WHEN** the user ingests with `--cookies cookies.txt` and YouTube still answers with the bot check
- **THEN** the message additionally says the cookies may be expired and suggests exporting fresh cookies or using a proxy

### Requirement: Unavailable video
When the video is private, deleted, members-only or otherwise unavailable, ingest SHALL exit
non-zero with a message that states the video is unavailable and why when YouTube says why, and
SHALL leave the library unchanged.

#### Scenario: Private video
- **WHEN** the user ingests a private video
- **THEN** the command exits non-zero, says the video is private, and the library is unchanged

### Requirement: JavaScript runtime warning
YouTube access needs a JavaScript runtime. When neither deno nor node is found on `PATH`, ingest
SHALL print a warning naming both and SHALL still attempt the download.

#### Scenario: No JavaScript runtime
- **WHEN** neither `deno` nor `node` is on `PATH` and the user runs ingest
- **THEN** a warning names deno and node as supported runtimes and the ingest is still attempted
