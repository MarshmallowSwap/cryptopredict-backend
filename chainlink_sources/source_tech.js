// CryptoPredict — Chainlink Functions source for TECH & AI markets
// APIs: GitHub (free), Wikipedia (free), HackerNews (free)
// Args: [question, marketId, targetProject, targetCompany]
// Returns: "YES" or "NO"

const question      = args[0] || "";
const targetProject = args[2] || "";  // e.g. "GPT-5", "iPhone 17"
const targetCompany = args[3] || "";  // e.g. "OpenAI", "Apple"
const q = question.toLowerCase();

let yesWon = false;

// GitHub releases check
if (q.includes("release") || q.includes("launch") || q.includes("open source")) {
  const repo = targetProject.replace(/\s+/g, "").toLowerCase();
  const company = targetCompany.replace(/\s+/g, "").toLowerCase();
  
  if (company && repo) {
    const ghResp = await Functions.makeHttpRequest({
      url: `https://api.github.com/repos/${company}/${repo}/releases/latest`,
      headers: { "User-Agent": "CryptoPredict-Oracle" }
    });
    if (!ghResp.error && ghResp.data?.tag_name) {
      yesWon = true; // A release exists
    }
  }
}

// Wikipedia check for IPO/product launches
if (!yesWon) {
  const searchTerm = encodeURIComponent(
    `${targetCompany} ${targetProject}`.trim() || question.slice(0, 60)
  );
  
  const wikiResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/api/rest_v1/page/summary/${searchTerm}`
  });
  
  if (!wikiResp.error) {
    const extract = (wikiResp.data?.extract || "").toLowerCase();
    yesWon = extract.includes("released") || extract.includes("launched") ||
             extract.includes("ipo") || extract.includes("announced") ||
             extract.includes("unveiled");
  }
}

// HackerNews as confirmation
if (!yesWon) {
  const hnResp = await Functions.makeHttpRequest({
    url: `https://hn.algolia.com/api/v1/search?query=${encodeURIComponent(targetProject || question.slice(0,40))}&tags=story&numericFilters=created_at_i>${Math.floor(Date.now()/1000)-86400*30}`
  });
  
  if (!hnResp.error) {
    const hits = hnResp.data?.hits || [];
    const projectLower = (targetProject || "").toLowerCase();
    const found = hits.some(h => 
      (h.title || "").toLowerCase().includes(projectLower) &&
      ((h.title || "").toLowerCase().includes("launch") ||
       (h.title || "").toLowerCase().includes("release") ||
       (h.title || "").toLowerCase().includes("announce"))
    );
    if (found) yesWon = true;
  }
}

return Functions.encodeString(yesWon ? "YES" : "NO");
