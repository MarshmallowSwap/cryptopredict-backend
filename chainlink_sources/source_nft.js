// CryptoPredict — Chainlink Functions source for NFT & GAMING markets
// APIs: Reservoir (free), OpenSea (free public), CoinGecko (free)
// Args: [question, marketId, targetCollection, targetValue, targetDirection]
// Returns: "YES" or "NO"

const question         = args[0] || "";
const targetCollection = args[2] || "";  // e.g. "boredapeyachtclub"
const targetValue      = parseFloat(args[3] || "0");
const targetDirection  = args[4] || "above";
const q = question.toLowerCase();

let yesWon = false;

// Reservoir API (free, no key for public data)
if (targetCollection) {
  const reservoirResp = await Functions.makeHttpRequest({
    url: `https://api.reservoir.tools/collections/v7?id=${targetCollection}&limit=1`,
    headers: { "x-api-key": "demo" }
  });
  
  if (!reservoirResp.error) {
    const collections = reservoirResp.data?.collections || [];
    if (collections.length > 0) {
      const floorPrice = collections[0].floorAsk?.price?.amount?.native || 0;
      if (targetValue !== 0) {
        yesWon = targetDirection === "above" 
          ? floorPrice >= targetValue 
          : floorPrice <= targetValue;
      }
    }
  }
}

// Gaming: check via Wikipedia or news
if (!yesWon && (q.includes("game") || q.includes("gaming") || q.includes("metaverse"))) {
  const searchTerm = encodeURIComponent(question.slice(0, 60));
  const wikiResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/api/rest_v1/page/summary/${searchTerm}`
  });
  
  if (!wikiResp.error) {
    const extract = (wikiResp.data?.extract || "").toLowerCase();
    yesWon = extract.includes("released") || extract.includes("launched") ||
             extract.includes("announced") || extract.includes("sold");
  }
}

return Functions.encodeString(yesWon ? "YES" : "NO");
