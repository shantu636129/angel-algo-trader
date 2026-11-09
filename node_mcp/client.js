const { Client } = require("@modelcontextprotocol/sdk/client/index.js");
const { SSEClientTransport } = require("@modelcontextprotocol/sdk/client/sse.js");

async function main() {
    const transport = new SSEClientTransport(
        new URL("https://shantu-mcp.duckdns.org/fs/sse")
    );

    const client = new Client(
        {
            name: "angelone-test-client",
            version: "1.0.0"
        },
        {
            capabilities: {}
        }
    );

    console.log("Connecting to MCP...");

    await client.connect(transport);

    console.log("MCP CONNECTED SUCCESSFULLY");

    const result = await client.listTools();

    console.log("\nAVAILABLE TOOLS:");

    for (const tool of result.tools) {
        console.log(`- ${tool.name}: ${tool.description || ""}`);
    }

    await transport.close();
}

main().catch((error) => {
    console.error("MCP CONNECTION FAILED");
    console.error(error);
    process.exit(1);
});
