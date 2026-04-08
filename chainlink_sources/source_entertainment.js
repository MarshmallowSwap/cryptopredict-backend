// CryptoPredict — Chainlink Functions source for ENTERTAINMENT markets
// APIs: Wikipedia (free), TMDb (free tier)
// Args: [question, marketId, targetAward, targetNominee]
// Returns: "YES" or "NO"

const question    = args[0] || "";
const targetAward = args[2] || "";  // e.g. "Oscar Best Picture"
const targetNominee = args[3] || ""; // e.g. "Oppenheimer"

// Search Wikipedia for the award results
const searchQuery = encodeURIComponent(
  targetAward || question.slice(0, 60)
);

const wikiResponse = await Functions.makeHttpRequest({
  url: `https://en.wikipedia.org/api/rest_v1/page/summary/${searchQuery}`
});

if (wikiResponse.error) {
  // Try search
  const searchResp = await Functions.makeHttpRequest({
    url: `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${searchQuery}&format=json&utf8=1`
  });
  if (searchResp.error) return Functions.encodeString("NO");
  
  const results = searchResp.data?.query?.search || [];
  if (results.length === 0) return Functions.encodeString("NO");
  
  // Check if nominee appears in top result
  const topSnippet = results[0].snippet?.toLowerCase() || "";
  const nominee = targetNominee.toLowerCase();
  const yesWon = nominee ? topSnippet.includes(nominee) : false;
  return Functions.encodeString(yesWon ? "YES" : "NO");
}

// Check Wikipedia extract for nominee winning
const extract = (wikiResponse.data?.extract || "").toLowerCase();
const nominee = targetNominee.toLowerCase();
const q = question.toLowerCase();

let yesWon = false;

if (nominee && extract.includes(nominee)) {
  // Look for winning language near the nominee
  const idx = extract.indexOf(nominee);
  const context = extract.slice(Math.max(0, idx - 100), idx + 200);
  yesWon = context.includes("won") || context.includes("winner") || 
           context.includes("received") || context.includes("awarded");
}

return Functions.encodeString(yesWon ? "YES" : "NO");
