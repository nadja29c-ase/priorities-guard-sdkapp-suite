Clarity V5 (Widget Integration)
Goal
Add UI widget to cluster_raw_thoughts tool. Widget renders clusters as visual cards.

File to Create
Path: mcp_server/clarity/widget.html
Content: The complete HTML provided below (copy exactly):
html<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Clarity clusters</title>
    <style>
      :root {
        --bg-primary: #ffffff;
        --bg-secondary: #f7f7f8;
        --bg-card: #ffffff;
        --text-primary: #0d0d0d;
        --text-secondary: #6e6e80;
        --text-muted: #8e8ea0;
        --border-color: #e5e5e6;
        --shadow: rgba(0, 0, 0, 0.05);
        --pill-bg: #ececf1;
        --pill-text: #353540;
      }

      .dark {
        --bg-primary: #212121;
        --bg-secondary: #2f2f2f;
        --bg-card: #2f2f2f;
        --text-primary: #ececec;
        --text-secondary: #b4b4b4;
        --text-muted: #8e8e8e;
        --border-color: #444444;
        --shadow: rgba(0, 0, 0, 0.2);
        --pill-bg: #444444;
        --pill-text: #ececec;
      }

      html, body {
        width: 100%;
        min-height: 100%;
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }

      body {
        padding: 16px;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
        font-size: 14px;
        line-height: 1.5;
      }

      main {
        width: 100%;
        max-width: 900px;
        margin: 0 auto;
      }

      .header {
        margin-bottom: 16px;
      }

      .title {
        margin: 0 0 4px;
        font-size: 16px;
        font-weight: 600;
        color: var(--text-primary);
      }

      .subtitle {
        margin: 0;
        font-size: 13px;
        color: var(--text-secondary);
      }

      .cluster-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 12px;
      }

      .cluster-card {
        border-radius: 12px;
        padding: 14px;
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        box-shadow: 0 1px 3px var(--shadow);
        display: flex;
        flex-direction: column;
        min-height: 120px;
      }

      .cluster-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 8px;
      }

      .cluster-name {
        font-size: 14px;
        font-weight: 600;
        color: var(--text-primary);
      }

      .priority-pill {
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
        background: var(--pill-bg);
        color: var(--pill-text);
        white-space: nowrap;
      }

      .cluster-summary {
        font-size: 13px;
        color: var(--text-secondary);
        margin-bottom: 10px;
      }

      .items-list {
        margin: 0;
        padding: 0;
        list-style: none;
        flex-grow: 1;
      }

      .items-list li {
        font-size: 13px;
        color: var(--text-primary);
        margin-bottom: 6px;
        display: flex;
        align-items: flex-start;
        gap: 8px;
      }

      .items-bullet {
        color: var(--text-muted);
        font-size: 13px;
        line-height: 1.4;
        flex-shrink: 0;
      }

      .items-text {
        flex: 1;
        line-height: 1.4;
        word-break: break-word;
        overflow: hidden;
        text-overflow: ellipsis;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
      }

      .why-relevant {
        margin-top: 10px;
        padding-top: 10px;
        border-top: 1px solid var(--border-color);
        font-size: 12px;
        color: var(--text-muted);
      }

      .empty-state {
        padding: 24px;
        text-align: center;
        font-size: 14px;
        color: var(--text-secondary);
        background: var(--bg-secondary);
        border-radius: 12px;
      }
    </style>
  </head>
  <body>
    <main>
      <div class="header">
        <p class="title">Clarity Board</p>
        <p class="subtitle">
          Your thoughts grouped into clusters. Use the chat to rename, split, or reprioritize them.
        </p>
      </div>
      <div id="cluster-root"></div>
    </main>

    <script type="module">
      const rootEl = document.querySelector("#cluster-root");

      const applyTheme = () => {
        const theme = window.openai?.theme ?? "light";
        document.body.classList.remove("light", "dark");
        document.body.classList.add(theme);
      };

      const getClustersFromToolOutput = () => {
        const clusters = window.openai?.toolOutput?.structuredContent?.clusters ?? [];
        if (!Array.isArray(clusters)) return [];
        return clusters;
      };

      const relevanceToLabel = (score) => {
        if (typeof score !== "number") return null;
        if (score >= 8) return "P1";
        if (score >= 5) return "P2";
        return "P3";
      };

      const truncateText = (text, maxLength = 80) => {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength).trim() + "…";
      };

      const render = () => {
        applyTheme();
        const clusters = getClustersFromToolOutput();
        rootEl.innerHTML = "";

        if (!clusters.length) {
          const empty = document.createElement("div");
          empty.className = "empty-state";
          empty.textContent = "No clusters yet. Ask in chat to organize your brain dump into clusters.";
          rootEl.appendChild(empty);
          return;
        }

        const grid = document.createElement("div");
        grid.className = "cluster-grid";

        clusters.forEach((cluster) => {
          const card = document.createElement("div");
          card.className = "cluster-card";

          const header = document.createElement("div");
          header.className = "cluster-header";

          const nameEl = document.createElement("div");
          nameEl.className = "cluster-name";
          nameEl.textContent = truncateText(cluster.name, 40) || "Untitled cluster";
          header.appendChild(nameEl);

          const pillLabel = relevanceToLabel(cluster.relevance_score);
          if (pillLabel) {
            const pill = document.createElement("div");
            pill.className = "priority-pill";
            pill.textContent = pillLabel;
            header.appendChild(pill);
          }

          card.appendChild(header);

          if (cluster.summary) {
            const summaryEl = document.createElement("div");
            summaryEl.className = "cluster-summary";
            summaryEl.textContent = truncateText(cluster.summary, 100);
            card.appendChild(summaryEl);
          }

          const items = Array.isArray(cluster.items) ? cluster.items : [];
          if (items.length) {
            const list = document.createElement("ul");
            list.className = "items-list";

            items.slice(0, 5).forEach((rawText) => {
              const li = document.createElement("li");
              const bullet = document.createElement("span");
              bullet.className = "items-bullet";
              bullet.textContent = "•";
              const text = document.createElement("span");
              text.className = "items-text";
              text.textContent = rawText;
              li.appendChild(bullet);
              li.appendChild(text);
              list.appendChild(li);
            });

            if (items.length > 5) {
              const more = document.createElement("li");
              more.innerHTML = `<span class="items-bullet"></span><span class="items-text" style="color: var(--text-muted)">+${items.length - 5} more</span>`;
              list.appendChild(more);
            }

            card.appendChild(list);
          }

          if (cluster.why_relevant) {
            const why = document.createElement("div");
            why.className = "why-relevant";
            why.textContent = truncateText(cluster.why_relevant, 120);
            card.appendChild(why);
          }

          grid.appendChild(card);
        });

        rootEl.appendChild(grid);
      };

      render();
      window.addEventListener("openai:set_globals", () => render(), { passive: true });
    </script>
  </body>
</html>

Changes to mcp_server/clarity/server.py
1. Add widget resource registration
Register the widget resource with FastMCP. Load HTML from widget.html file.
Widget URI: ui://widget/clarity-clusters.html
MimeType: text/html+skybridge
Resource _meta:
python{
    "openai/widgetPrefersBorder": True,
    "openai/widgetDescription": "Visual board showing business thought clusters as cards."
}
2. Update cluster_raw_thoughts tool
Tool _meta (add to tool decorator):
python_meta={
    "openai/outputTemplate": "ui://widget/clarity-clusters.html",
    "openai/toolInvocation/invoking": "Organizing your thoughts into clusters…",
    "openai/toolInvocation/invoked": "Here's your Clarity board."
}
Tool return format — change to return:
python{
    "content": [{"type": "text", "text": "I've organized your thoughts into clusters."}],
    "structuredContent": {
        "clusters": [...]  # enriched clusters from tools.py
    }
}

Changes to mcp_server/clarity/tools.py
Update cluster_raw_thoughts return to match expected schema:
pythondef cluster_raw_thoughts(clusters: list[dict]) -> dict:
    enriched = [
        {
            "name": c["name"],
            "items": c["items"],
            "summary": f"{c['name']} related tasks",
            "relevance_score": len(c["items"])
        }
        for c in clusters
    ]
    
    return {
        "content": [{"type": "text", "text": "I've organized your thoughts into clusters."}],
        "structuredContent": {
            "clusters": enriched
        }
    }

Do NOT Change

Other tools (identify_most_relevant_clusters, specify_next_steps)
Tool descriptions
Port configuration
Business-only domain restrictions

