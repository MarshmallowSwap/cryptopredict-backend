// CryptoPredict — Chainlink Functions source for POLITICA markets
// APIs: Wikipedia (free), NewsAPI free tier
// Args: [question, marketId, targetCandidate, targetEvent, targetCountry]
// Returns: "YES" or "NO"

const question        = args[0] || "";
const targetCandidate = args[2] || "";
const targetEvent     = args[3] || "";  // e.g. "election 2024", "bill", "treaty"
const targetCountry   = args[4] || "";
const q = question.toLowerCase();

let yesWon = false;

// Wikipedia search for election/political results
const searchTerm = encodeURIComponent(
  `${targetEvent} ${targetCountry} ${targetCandidate}`.trim() || question.slice(0, 60)
);

const wikiResp = await Functions.makeHttpRequest({
  url: `https://en.wikipedia.org/api/rest_v1/page/summary/${searchTerm}`
});

if (!wikiResp.error) {
  const extract = (wikiResp.data?.extract || "").toLowerCase();
  const candidate = targetCandidate.toLowerCase();
  
  if (candidate && extract.includes(candidate)) {
    const idx = extract.indexOf(candidate);
    const context = extract.slice(Math.max(0, idx - 150), idx + 300);
    yesWon = context.includes("won") || context.includes("elected") ||
             context.includes("winner") || context.includes("victory") ||
             context.includes("approved") || context.includes("passed");
  }
}

// Fallback: search Wikipedia
if (!yesWon) {
  const searchResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${searchTerm}&format=json&utf8=1`
  });
  
  if (!searchResp.error) {
    const results = searchResp.data?.query?.search || [];
    for (const result of results.slice(0, 3)) {
      const snippet = result.snippet?.toLowerCase() || "";
      const candidate = targetCandidate.toLowerCase();
      if (candidate && snippet.includes(candidate)) {
        yesWon = snippet.includes("won") || snippet.includes("elected") ||
                 snippet.includes("winner") || snippet.includes("approved");
        if (yesWon) break;
      }
    }
  }
}

return Functions.encodeString(yesWon ? "YES" : "NO");
