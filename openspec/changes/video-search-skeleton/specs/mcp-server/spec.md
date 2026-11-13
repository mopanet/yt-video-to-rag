# Spec Delta

## Purpose

Lets the user ask questions about the ingested videos from an MCP client such as Claude Code or
Claude Desktop, in any language, with the client writing the answer from the passages the
library returns and citing each claim with the video, the exact moment and the original words.

## ADDED Requirements

### Requirement: Stdio MCP server
`video-to-rag mcp` SHALL run an MCP server over standard input and output, using the same library
location rules as the other commands. Standard output SHALL carry only protocol messages; any log
output SHALL go to standard error.

#### Scenario: Tools offered
- **WHEN** an MCP client connects and lists the tools
- **THEN** exactly one tool, `search`, is offered

#### Scenario: Clean protocol stream
- **WHEN** the server starts, answers a search and shuts down
- **THEN** every line it wrote to standard output is a protocol message

### Requirement: Search tool
The `search` tool SHALL take `queries` (one to five non-blank strings), an optional `channel` and
an optional `limit`, with the same rules as the search command, and SHALL return the hits with
every field of a search hit both as structured data and as readable text. Invalid input SHALL
produce a tool error and the server SHALL keep running.

#### Scenario: Successful tool call
- **WHEN** the client calls `search` with `queries: ["hogyan javítsam a fókuszomat", "how to improve focus"]` and `limit: 5`
- **THEN** up to five hits are returned, each with title, channel, date, time range, timestamped link, language and passage text

#### Scenario: Invalid input
- **WHEN** the client calls `search` with an empty `queries` list
- **THEN** the call returns a tool error stating the one-to-five non-blank rule, and a following valid call succeeds

#### Scenario: Empty library
- **WHEN** the client calls `search` before anything was ingested
- **THEN** the call returns no hits and a message that the library is empty and how to fill it

### Requirement: Answering instructions for the client
The server SHALL give the client instructions to: search with the question in the user's language
and translated into the videos' language (English when unknown); answer in the user's language;
back every claim with a numbered citation naming the video title and its timestamped link; quote
the original passage, adding a translation when its language differs from the user's.

#### Scenario: Instructions delivered
- **WHEN** an MCP client initializes a session with the server
- **THEN** the instructions it receives contain the rules on query languages, answer language, numbered timestamped citations and original-language quotes with translation

### Requirement: Attribution discipline
The instructions SHALL tell the client to attribute to a channel only what the returned passages
say, and to state plainly when the passages do not cover the question instead of filling the gap
with outside knowledge presented as the channel's view.

#### Scenario: Question not covered
- **WHEN** an MCP client initializes a session with the server
- **THEN** the instructions it receives tell it to say when the passages do not answer the question and not to present outside knowledge as the channel's view

### Requirement: Read-only and offline from YouTube
The MCP server SHALL NOT modify the library and SHALL NOT contact YouTube.

#### Scenario: Library untouched by searching
- **WHEN** the client makes any number of `search` calls
- **THEN** the library file's content is unchanged and no request is made to YouTube
