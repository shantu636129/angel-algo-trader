const express = require("express");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { exec } = require("child_process");

const app = express();
const PORT = 8003;

app.use(express.json({ limit: "50mb" }));

const sessions = new Map();

function sendSSE(session, message) {
    session.res.write(
        `event: message\n` +
        `data: ${JSON.stringify(message)}\n\n`
    );
}

function toolResult(text) {
    return {
        content: [
            {
                type: "text",
                text: typeof text === "string"
                    ? text
                    : JSON.stringify(text, null, 2)
            }
        ]
    };
}

function executeCommand(command, timeout = 30000) {
    return new Promise((resolve) => {
        exec(
            command,
            {
                shell: "/bin/bash",
                timeout,
                maxBuffer: 10 * 1024 * 1024
            },
            (error, stdout, stderr) => {
                resolve({
                    success: !error,
                    stdout,
                    stderr,
                    exitCode: error ? error.code : 0
                });
            }
        );
    });
}

// ============================================================
// HEALTH
// ============================================================

app.get("/health", (req, res) => {
    res.json({
        status: "online",
        server: "AngelOne MCP",
        authentication: "none",
        oauth: "disabled",
        node_version: process.version,
        hostname: os.hostname()
    });
});

// ============================================================
// SSE
// ============================================================

app.get("/sse", (req, res) => {

    const sessionId = crypto.randomUUID();

    res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    });

    const session = {
        res,
        createdAt: Date.now()
    };

    sessions.set(sessionId, session);

    console.log("SSE SESSION CREATED:", sessionId);

    res.write(
        `event: endpoint\n` +
        `data: /messages?sessionId=${sessionId}\n\n`
    );

    req.on("close", () => {
        console.log("SSE SESSION CLOSED:", sessionId);
        sessions.delete(sessionId);
    });
});

// ============================================================
// MCP MESSAGES
// ============================================================

app.post("/messages", async (req, res) => {

    const sessionId = req.query.sessionId;
    const message = req.body;

    console.log(
        "MCP REQUEST:",
        JSON.stringify(message)
    );

    const session = sessions.get(sessionId);

    if (!session) {
        return res.status(400).json({
            error: "Invalid or expired session"
        });
    }

    // ========================================================
    // INITIALIZE
    // ========================================================

    if (message.method === "initialize") {

        sendSSE(session, {
            jsonrpc: "2.0",
            id: message.id,
            result: {
                protocolVersion: "2024-11-05",
                capabilities: {
                    tools: {}
                },
                serverInfo: {
                    name: "AngelOne MCP",
                    version: "1.0.0"
                }
            }
        });

        return res.status(202).end();
    }

    // ========================================================
    // INITIALIZED
    // ========================================================

    if (message.method === "notifications/initialized") {
        return res.status(202).end();
    }

    // ========================================================
    // TOOLS LIST
    // ========================================================

    if (message.method === "tools/list") {

        sendSSE(session, {
            jsonrpc: "2.0",
            id: message.id,
            result: {
                tools: [

                    {
                        name: "ping",
                        description: "Test MCP server connection.",
                        inputSchema: {
                            type: "object",
                            properties: {}
                        }
                    },

                    {
                        name: "get_status",
                        description: "Get MCP server and system status.",
                        inputSchema: {
                            type: "object",
                            properties: {}
                        }
                    },

                    {
                        name: "list_files",
                        description: "List files and directories at any filesystem path.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string",
                                    description: "Directory path"
                                }
                            },
                            required: ["path"]
                        }
                    },

                    {
                        name: "read_file",
                        description: "Read the contents of any file.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string",
                                    description: "File path"
                                }
                            },
                            required: ["path"]
                        }
                    },

                    {
                        name: "write_file",
                        description: "Create or overwrite a file with supplied content.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string"
                                },
                                content: {
                                    type: "string"
                                }
                            },
                            required: ["path", "content"]
                        }
                    },

                    {
                        name: "append_file",
                        description: "Append content to an existing file.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string"
                                },
                                content: {
                                    type: "string"
                                }
                            },
                            required: ["path", "content"]
                        }
                    },

                    {
                        name: "delete_file",
                        description: "Delete a file.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string"
                                }
                            },
                            required: ["path"]
                        }
                    },

                    {
                        name: "create_directory",
                        description: "Create a directory recursively.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string"
                                }
                            },
                            required: ["path"]
                        }
                    },

                    {
                        name: "search_files",
                        description: "Search text recursively in files using grep.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string"
                                },
                                search: {
                                    type: "string"
                                }
                            },
                            required: ["path", "search"]
                        }
                    },

                    {
                        name: "get_file_info",
                        description: "Get file metadata and permissions.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string"
                                }
                            },
                            required: ["path"]
                        }
                    },

                    {
                        name: "run_script",
                        description: "Execute a shell command or script.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                command: {
                                    type: "string"
                                }
                            },
                            required: ["command"]
                        }
                    },

                    {
                        name: "get_logs",
                        description: "Read the last lines of a log file.",
                        inputSchema: {
                            type: "object",
                            properties: {
                                path: {
                                    type: "string"
                                },
                                lines: {
                                    type: "number"
                                }
                            },
                            required: ["path"]
                        }
                    },

                    {
                        name: "get_processes",
                        description: "List running processes.",
                        inputSchema: {
                            type: "object",
                            properties: {}
                        }
                    },

                    {
                        name: "get_crontab",
                        description: "View current user's crontab.",
                        inputSchema: {
                            type: "object",
                            properties: {}
                        }
                    }

                ]
            }
        });

        return res.status(202).end();
    }

    // ========================================================
    // TOOL CALL
    // ========================================================

    if (
        message.method === "tools/call"
    ) {

        const name = message.params?.name;
        const args = message.params?.arguments || {};

        try {

            // ------------------------------------------------
            // PING
            // ------------------------------------------------

            if (name === "ping") {

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(
                        "AngelOne MCP is connected successfully."
                    )
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // STATUS
            // ------------------------------------------------

            if (name === "get_status") {

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult({
                        status: "online",
                        server: "AngelOne MCP",
                        authentication: "none",
                        oauth: "disabled",
                        node_version: process.version,
                        platform: process.platform,
                        hostname: os.hostname()
                    })
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // LIST FILES
            // ------------------------------------------------

            if (name === "list_files") {

                const target = args.path;

                const entries = fs.readdirSync(
                    target,
                    { withFileTypes: true }
                );

                const result = entries.map(entry => ({
                    name: entry.name,
                    type: entry.isDirectory()
                        ? "directory"
                        : "file",
                    path: path.join(target, entry.name)
                }));

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(result)
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // READ FILE
            // ------------------------------------------------

            if (name === "read_file") {

                const content = fs.readFileSync(
                    args.path,
                    "utf8"
                );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(content)
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // WRITE FILE
            // ------------------------------------------------

            if (name === "write_file") {

                fs.writeFileSync(
                    args.path,
                    args.content,
                    "utf8"
                );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(
                        `File written successfully: ${args.path}`
                    )
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // APPEND FILE
            // ------------------------------------------------

            if (name === "append_file") {

                fs.appendFileSync(
                    args.path,
                    args.content,
                    "utf8"
                );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(
                        `Content appended successfully: ${args.path}`
                    )
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // DELETE FILE
            // ------------------------------------------------

            if (name === "delete_file") {

                fs.unlinkSync(args.path);

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(
                        `File deleted successfully: ${args.path}`
                    )
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // CREATE DIRECTORY
            // ------------------------------------------------

            if (name === "create_directory") {

                fs.mkdirSync(
                    args.path,
                    { recursive: true }
                );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(
                        `Directory created: ${args.path}`
                    )
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // SEARCH FILES
            // ------------------------------------------------

            if (name === "search_files") {

                const command =
                    `grep -RIn --exclude-dir=node_modules ` +
                    `"${args.search.replace(/"/g, '\\"')}" ` +
                    `"${args.path}" 2>/dev/null | head -500`;

                const result =
                    await executeCommand(command);

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(result.stdout || result.stderr)
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // FILE INFO
            // ------------------------------------------------

            if (name === "get_file_info") {

                const stats =
                    fs.statSync(args.path);

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult({
                        path: args.path,
                        size: stats.size,
                        isFile: stats.isFile(),
                        isDirectory: stats.isDirectory(),
                        created: stats.birthtime,
                        modified: stats.mtime,
                        accessed: stats.atime,
                        permissions:
                            (stats.mode & 0o777).toString(8)
                    })
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // RUN SCRIPT
            // ------------------------------------------------

            if (name === "run_script") {

                const result =
                    await executeCommand(
                        args.command,
                        120000
                    );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(result)
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // GET LOGS
            // ------------------------------------------------

            if (name === "get_logs") {

                const lines =
                    args.lines || 100;

                const result =
                    await executeCommand(
                        `tail -n ${Number(lines)} "${args.path}"`,
                        30000
                    );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(result.stdout || result.stderr)
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // GET PROCESSES
            // ------------------------------------------------

            if (name === "get_processes") {

                const result =
                    await executeCommand(
                        "ps aux",
                        30000
                    );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(result.stdout)
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // GET CRONTAB
            // ------------------------------------------------

            if (name === "get_crontab") {

                const result =
                    await executeCommand(
                        "crontab -l 2>&1",
                        30000
                    );

                sendSSE(session, {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: toolResult(result.stdout)
                });

                return res.status(202).end();
            }

            // ------------------------------------------------
            // UNKNOWN TOOL
            // ------------------------------------------------

            sendSSE(session, {
                jsonrpc: "2.0",
                id: message.id,
                error: {
                    code: -32601,
                    message: `Unknown tool: ${name}`
                }
            });

            return res.status(202).end();

        } catch (error) {

            sendSSE(session, {
                jsonrpc: "2.0",
                id: message.id,
                result: {
                    isError: true,
                    content: [
                        {
                            type: "text",
                            text: error.message
                        }
                    ]
                }
            });

            return res.status(202).end();
        }
    }

    return res.status(202).end();
});

// ============================================================
// START SERVER
// ============================================================

app.listen(
    PORT,
    "127.0.0.1",
    () => {

        console.log(
            `AngelOne MCP running on http://127.0.0.1:${PORT}`
        );

        console.log(
            "Filesystem access: unrestricted"
        );

        console.log(
            "Authentication: none"
        );

        console.log(
            "OAuth: disabled"
        );
    }
);
