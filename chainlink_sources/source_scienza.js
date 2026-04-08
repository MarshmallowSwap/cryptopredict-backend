// CryptoPredict — Chainlink Functions source for SCIENZA markets
// APIs: NASA (free), Wikipedia (free)
// Args: [question, marketId, targetMission, targetDate]
// Returns: "YES" or "NO"

const question      = args[0] || "";
const targetMission = args[2] || "";
const q = question.toLowerCase();

let yesWon = false;

// NASA APOD / missions
if (q.includes("nasa") || q.includes("space") || q.includes("spazio") || 
    q.includes("rocket") || q.includes("mission")) {
  
  const nasaResp = await Functions.makeHttpRequest({
    url: "https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY&count=1"
  });
  
  // For mission-specific queries, use Wikipedia
  const searchTerm = encodeURIComponent(targetMission || q.slice(0, 50));
  const wikiResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/api/rest_v1/page/summary/${searchTerm}`
  });
  
  if (!wikiResp.error) {
    const extract = (wikiResp.data?.extract || "").toLowerCase();
    yesWon = extract.includes("success") || extract.includes("launched") ||
             extract.includes("completed") || extract.includes("approved");
  }

} else if (q.includes("fda") || q.includes("approved") || q.includes("medicine")) {
  // Medical/FDA approvals via Wikipedia
  const searchTerm = encodeURIComponent(question.slice(0, 60));
  const wikiResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${searchTerm}&format=json`
  });
  
  if (!wikiResp.error) {
    const results = wikiResp.data?.query?.search || [];
    if (results.length > 0) {
      const snippet = results[0].snippet?.toLowerCase() || "";
      yesWon = snippet.includes("approved") || snippet.includes("success") ||
               snippet.includes("launched");
    }
  }

} else {
  // Generic Wikipedia search
  const searchTerm = encodeURIComponent(question.slice(0, 60));
  const wikiResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/api/rest_v1/page/summary/${searchTerm}`
  });
  
  if (!wikiResp.error) {
    const extract = (wikiResp.data?.extract || "").toLowerCase();
    yesWon = extract.includes("yes") || extract.includes("approved") ||
             extract.includes("confirmed") || extract.includes("success");
  }
}

return Functions.encodeString(yesWon ? "YES" : "NO");
