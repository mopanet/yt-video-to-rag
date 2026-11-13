# Spec Delta

## Purpose

Lets a user install video-to-rag as a standalone command-line tool on their own machine, tell
which version they run, and serve the installed copy's library to an MCP client, without a
development checkout.

## ADDED Requirements

### Requirement: Standalone installation
The package built from the repository SHALL install into an isolated tool environment and provide
a `video-to-rag` command with the `ingest`, `search` and `mcp` commands. The installed command
SHALL work from any directory, without the repository or its development environment.

#### Scenario: Commands of the installed tool
- **WHEN** the package built from the repository is installed into a fresh tool environment and `video-to-rag --help` is run
- **THEN** it exits 0 and lists `ingest`, `search` and `mcp`

#### Scenario: Installed search outside the repository
- **WHEN** the installed `video-to-rag search "focus" --data-dir <empty directory>` is run from a directory outside the repository, with an empty model cache
- **THEN** it exits 0, reports that the library is empty and how to fill it, creates no library file and downloads no embedding model

### Requirement: Version reporting
`video-to-rag --version` SHALL print `video-to-rag <version>` to standard output and exit 0, where
`<version>` is the version of the installed package. It SHALL not open a library, load the
embedding model or contact the network.

#### Scenario: Version of the installed package
- **WHEN** version 0.1.0 is installed and `video-to-rag --version` is run
- **THEN** standard output is `video-to-rag 0.1.0` and the exit code is 0

#### Scenario: Version with nothing set up
- **WHEN** `video-to-rag --version` is run with no library and an empty model cache
- **THEN** it succeeds, and no library file or model cache entry is created

### Requirement: Installed MCP server
An MCP client that starts the installed command as `video-to-rag mcp` SHALL be able to connect
and list the tools. Starting the server and listing the tools SHALL not download the embedding
model.

#### Scenario: Client connects to the installed server
- **WHEN** an MCP client starts the installed `video-to-rag mcp --data-dir <empty directory>` over standard input and output and lists the tools
- **THEN** exactly one tool, `search`, is offered

#### Scenario: Startup with an empty model cache
- **WHEN** the model cache is empty and an MCP client connects to the installed server and lists the tools
- **THEN** the listing succeeds and no embedding model is downloaded
