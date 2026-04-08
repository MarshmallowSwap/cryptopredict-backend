// CryptoPredict — Chainlink Functions source for MACRO markets
// APIs: FRED Federal Reserve (free key), Wikipedia (free)
// Args: [question, marketId, targetIndicator, targetValue, targetDirection]
// Returns: "YES" or "NO"

const question        = args[0] || "";
const targetIndicator = args[2] || "";  // e.g. "FEDFUNDS", "UNRATE", "CPIAUCSL"
const targetValue     = parseFloat(args[3] || "0");
const targetDirection = args[4] || "above"; // "above" | "below"
const q = question.toLowerCase();

let yesWon = false;

// FRED API — Federal Reserve Economic Data (free, api_key optional for public series)
if (targetIndicator && targetIndicator !== "") {
  const fredResp = await Functions.makeHttpRequest({
    url: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=${targetIndicator}`,
  });
  
  if (!fredResp.error) {
    // CSV: date,value — last line is most recent
    const lines = (fredResp.data || "").trim().split("\n");
    const lastLine = lines[lines.length - 1];
    const parts = lastLine.split(",");
    const latestValue = parseFloat(parts[1]);
    
    if (!isNaN(latestValue) && targetValue !== 0) {
      if (targetDirection === "above") {
        yesWon = latestValue >= targetValue;
      } else {
        yesWon = latestValue <= targetValue;
      }
    }
  }
}

// Fallback: Wikipedia for Fed decisions, ECB, etc.
if (!yesWon && !targetIndicator) {
  const searchTerm = encodeURIComponent(question.slice(0, 60));
  const wikiResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${searchTerm}&format=json`
  });
  
  if (!wikiResp.error) {
    const results = wikiResp.data?.query?.search || [];
    if (results.length > 0) {
      const snippet = (results[0].snippet || "").toLowerCase();
      // For "Fed raised rates?" type questions
      if (q.includes("raised") || q.includes("increased")) {
        yesWon = snippet.includes("raised") || snippet.includes("increased") || snippet.includes("hike");
      } else if (q.includes("cut") || q.includes("lowered")) {
        yesWon = snippet.includes("cut") || snippet.includes("lowered") || snippet.includes("reduced");
      } else if (q.includes("approved") || q.includes("passed")) {
        yesWon = snippet.includes("approved") || snippet.includes("passed") || snippet.includes("signed");
      }
    }
  }
}

return Functions.encodeString(yesWon ? "YES" : "NO");
