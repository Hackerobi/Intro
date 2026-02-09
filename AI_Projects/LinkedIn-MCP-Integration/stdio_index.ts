import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { RestliClient as LinkedinClient } from "linkedin-api-client";
import axios, { isAxiosError } from "axios";
import { z } from "zod";

const accessToken = process.env.LINKEDIN_ACCESS_TOKEN;

if (!accessToken) {
  console.error("ERROR: LINKEDIN_ACCESS_TOKEN environment variable is required.");
  process.exit(1);
}

const linkedinClient = new LinkedinClient();

const server = new McpServer(
  {
    name: "LinkedIn",
    version: "0.3.0",
  },
  {
    capabilities: { tools: {} },
    instructions:
      "This MCP server helps with LinkedIn tasks. It can get info on the logged-in user and create posts on their behalf.",
  }
);

// ──────────────────────────────────────────────
// Tool: user-info  (OpenID Connect userinfo endpoint)
// ──────────────────────────────────────────────
server.tool(
  "user-info",
  "Get information about the currently logged in LinkedIn user",
  async () => {
    try {
      // Use the OpenID Connect userinfo endpoint (requires 'openid' + 'profile' scopes)
      const { data } = await axios.get("https://api.linkedin.com/v2/userinfo", {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      const userInfo = z
        .object({
          sub: z.string(),
          name: z.string().optional(),
          given_name: z.string().optional(),
          family_name: z.string().optional(),
          picture: z.string().url().optional(),
          email: z.string().email().optional(),
          email_verified: z.boolean().optional(),
          locale: z
            .object({
              country: z.string().optional(),
              language: z.string().optional(),
            })
            .optional(),
        })
        .parse(data);

      const displayName =
        userInfo.name ||
        [userInfo.given_name, userInfo.family_name].filter(Boolean).join(" ") ||
        "Unknown";

      const content: Array<{ type: "text" | "image"; text?: string; mimeType?: string; data?: string }> = [
        {
          type: "text" as const,
          text: [
            `Currently logged in user: ${displayName}`,
            userInfo.email ? `Email: ${userInfo.email}` : null,
            `LinkedIn Member ID (sub): ${userInfo.sub}`,
          ]
            .filter(Boolean)
            .join("\n"),
        },
      ];

      // Fetch profile picture if available
      if (userInfo.picture) {
        try {
          const { data: imgData, headers } = await axios.get(userInfo.picture, {
            responseType: "arraybuffer",
          });
          const mimeType = headers["content-type"] || "image/jpeg";
          const base64Data = Buffer.from(imgData, "binary").toString("base64");
          content.push({
            type: "image" as any,
            mimeType,
            data: base64Data,
          });
        } catch {
          // If image fetch fails, just skip it
        }
      }

      return { content };
    } catch (e) {
      return handleError(e);
    }
  }
);

// ──────────────────────────────────────────────
// Tool: create-post  (LinkedIn Posts API v2)
// ──────────────────────────────────────────────
server.tool(
  "create-post",
  "Create a new post on LinkedIn",
  { content: z.string().describe("The text content of the LinkedIn post") },
  async ({ content }) => {
    try {
      // Get the user's sub (member ID) via userinfo
      const { data: userInfo } = await axios.get("https://api.linkedin.com/v2/userinfo", {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      const { sub: personId } = z.object({ sub: z.string() }).parse(userInfo);

      await linkedinClient.create({
        resourcePath: "/posts",
        entity: {
          author: `urn:li:person:${personId}`,
          commentary: content,
          visibility: "PUBLIC",
          distribution: {
            feedDistribution: "MAIN_FEED",
            targetEntities: [],
            thirdPartyDistributionChannels: [],
          },
          lifecycleState: "PUBLISHED",
          isReshareDisabledByAuthor: false,
        },
        accessToken,
      });

      return {
        content: [
          { type: "text" as const, text: "Your post has been successfully created on LinkedIn!" },
        ],
      };
    } catch (e) {
      return handleError(e);
    }
  }
);

// ──────────────────────────────────────────────
// Error handler
// ──────────────────────────────────────────────
function handleError(e: unknown) {
  if (isAxiosError(e)) {
    return {
      isError: true,
      content: [
        {
          type: "text" as const,
          text: `[${e.response?.status} ${e.response?.statusText}] LinkedIn API error: ${
            e.response?.data?.message || JSON.stringify(e.response?.data)
          }`,
        },
      ],
    };
  }

  if (e instanceof z.ZodError) {
    return {
      isError: true,
      content: [
        {
          type: "text" as const,
          text: `Unexpected LinkedIn API response format: ${JSON.stringify(e.issues)}`,
        },
      ],
    };
  }

  return {
    isError: true,
    content: [{ type: "text" as const, text: JSON.stringify(e) }],
  };
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("LinkedIn MCP Server v0.3.0 running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
