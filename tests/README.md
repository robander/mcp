# End-to-End Tests for OCI MCP Servers

## Introduction

This directory contains end-to-end tests for the OCI MCP Servers using the [Behave framework](https://behave.readthedocs.io/en/latest/).

## Prerequisites

1. Ensure that you have `uv` installed from the [Quick Start](https://github.com/oracle/mcp#quick-start) section of the main README.
2. Ensure that you have your local development environment set up from the [Local development](https://github.com/oracle/mcp#local-development) section of the main README.
3. Ensure that you have downloaded `ollama`, started the `ollama` server, and fetched a large language model (e.g. gpt-oss:20b) from the [Client configuration - MCPHost](https://github.com/oracle/mcp#mcphost) section of the main README.
   1. When following the instructions in the step above, there is no need to start `mcphost` for these E2E tests. You only need to install and start `ollama` for running these tests.

## Configuration

1. In the `tests/e2e/features` directory, copy `.env.template` to `.env`.
2. Fill in the required environment variables in `.env`:
   - MCP_HOST_FILE: The .json configuration file holding your MCP server configurations. Defaults to the absolute path of the existing tests/e2e/features/mcphost.json file.
   - URL: The URL to send the LLM prompts to. Defaults to http://localhost:8000/api/chat (Ollama's chat endpoint).
   - MODEL: LLM model that you are running. This should be the model that you fetched in the prerequisites section. Defaults to gpt-oss:20b.

   You can copy the following into a `.env` file
   ```bash
   MCP_HOST_FILE=
   URL=
   MODEL=
   ```

## Running the Tests

1. If you have not already activated your virtual environment from the [Local development](https://github.com/oracle/mcp#local-development) section, please do so.
2. In the `tests` directory, install the test dependencies using this command: `uv pip install .`
3. In the `tests/e2e` directory, run all of the tests by using this command: `behave`
   1. Run specific features by using this command: `behave features/<name of your feature file>`. Example: `behave features/oci-compute-mcp-server.feature`
   2. Run specific scenarios by using this command: `behave -n "Name of your scenario"`. Example: `behave -n "OCI Compute MCP Server"`

## Adding New End-to-End Tests

The E2E tests use Behave feature files to exercise MCP tools through `ollama-mcp-bridge`. For most OCI services, the bridge starts the MCP servers from `tests/e2e/features/mcphost.json`, sends model prompts to the configured chat endpoint, and routes OCI SDK calls through the local mock OCI service in `tests/e2e/features/mocks`.

1. Add or update a feature file in `tests/e2e/features`.
   - Use the existing naming convention: `oci-<service-name>-mcp-server.feature`.
   - Keep scenarios focused on one user-visible flow or tool capability.
   - Reuse the shared setup steps unless your test intentionally bypasses the bridge:
     ```gherkin
     Given the MCP server is running with OCI tools
     And the ollama model with the tools is properly working
     When I send a request with the prompt "list my buckets"
     Then the response should contain a list of buckets available
     ```
   - Prefer deterministic prompts that name the mock resource or describe one clear action. Avoid prompts that depend on live tenancy data, the current date, or model creativity.

2. Add step definitions in `tests/e2e/features/steps`.
   - Use the existing naming convention: `oci-<service-name>-mcp-server-steps.py`.
   - Put shared prompt and bridge steps in `general-prompts.py` only when they are service-neutral.
   - Keep assertions tolerant of response formatting but strict about mock data. For example, assert that the response content includes stable mock names, OCIDs, statuses, or field labels instead of matching a full natural-language response.
   - Use the standard Python copyright and UPL license header on new Python files:
     ```python
     """
     Copyright (c) 2026, Oracle and/or its affiliates.
     Licensed under the Universal Permissive License v1.0 as shown at
     https://oss.oracle.com/licenses/upl.
     """
     ```

3. Add mock OCI responses when the scenario calls an OCI API.
   - Add deterministic mock data in `tests/e2e/features/mocks/services/<service>_data.py`.
   - Add Flask routes in `tests/e2e/features/mocks/services/<service>_routes.py`.
   - Expose a blueprint named `<service>_bp`; `mock_oci_server.py` automatically registers every `*_routes.py` module that follows this pattern.
   - Match the OCI SDK's expected REST path, method, query parameters, and response shape closely enough for the MCP server code under test.
   - Use mock OCIDs, names, and timestamps consistently. Do not require real OCI credentials or live OCI resources.

4. Register a new MCP server when needed.
   - If the feature covers a server that is not already in `tests/e2e/features/mcphost.json`, add an entry for it.
   - Configure the entry the same way as the existing OCI server entries: set `OCI_CONFIG_FILE`, route `HTTP_PROXY` and `HTTPS_PROXY` to `http://127.0.0.1:5000`, and disable SSL verification for the local mock service.
   - If the server needs test-only import behavior, follow the existing entries that run `python -c` with `PYTHONPATH` and `mocks/sitecustomize.py`.

5. Validate the new test locally.
   - From `tests`, install or refresh dependencies:
     ```bash
     uv pip install .
     ```
   - From `tests/e2e`, run the new feature:
     ```bash
     behave features/oci-<service-name>-mcp-server.feature
     ```
   - From the repository root, run the repository checks before opening a pull request:
     ```bash
     make lint
     make test
     ```

When adding new E2E coverage, also follow the repository contribution guidelines in `CONTRIBUTING.md`: update relevant documentation, describe how the change was tested in the pull request, and sign commits with the Oracle Contributor Agreement sign-off.

## Notes

- The tests use the configuration from the `.env` file.
- The `mcphost.json` file is used to configure the MCP server.

----
<small>Copyright (c) 2025, 2026, Oracle and/or its affiliates. Licensed under the [Universal Permissive License v1.0](https://oss.oracle.com/licenses/upl).</small>
