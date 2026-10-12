# Agents

Subagents for Claude Code. Copy them into `.claude/agents/` (or `~/.claude/agents/`) to make them available, then ask Claude to use one by name.

| Agent | Use it for |
|-------|-----------|
| `performance-analyst` | Reviewing backtest results from the strategy tester |
| `strategy-reality-checker` | Auditing a strategy before trusting it: sample size, repainting, costs, overfitting. Defaults to "NEEDS WORK" |
| `market-researcher` | A falsifiable trade thesis for a symbol: bull/bear case, levels, invalidation |
| `mcp-builder` | Adding or changing MCP tools in `src/tools` + `src/core` |
| `code-reviewer` | Reviewing JS and Pine changes for correctness, injection safety and payload size |

## Attribution

`strategy-reality-checker`, `market-researcher`, `mcp-builder` and `code-reviewer` are adapted from
[msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) (commit `f99f6aa`):
"Reality Checker", "Investment Researcher", "MCP Builder" and "Code Reviewer". They were rewritten
to use this repo's TradingView MCP tools and conventions.

```
MIT License

Copyright (c) 2025 AgentLand Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
