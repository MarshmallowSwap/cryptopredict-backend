// CryptoPredict — Chainlink Functions source for SPORT markets
// APIs: ESPN (free, no key required)
// Args: [question, marketId, targetTeam, targetEvent, targetDate]
// Returns: "YES" or "NO"

const question   = args[0] || "";
const targetTeam = args[2] || "";
const targetEvent= args[3] || "";  // e.g. "NBA", "NFL", "F1", "MMA"
const targetDate = args[4] || "";

// Detect sport from question/event
let apiUrl = "";
const q = question.toLowerCase();

if (q.includes("nba") || targetEvent === "NBA") {
  // NBA scoreboard
  apiUrl = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard";
} else if (q.includes("nfl") || targetEvent === "NFL") {
  apiUrl = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard";
} else if (q.includes("f1") || q.includes("formula 1") || targetEvent === "F1") {
  apiUrl = "https://ergast.com/api/f1/current/last/results.json";
} else if (q.includes("ufc") || q.includes("mma") || targetEvent === "MMA") {
  // UFC via ESPN
  apiUrl = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard";
} else if (q.includes("premier league") || q.includes("football") || targetEvent === "EPL") {
  apiUrl = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard";
} else {
  // Generic ESPN search
  apiUrl = `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams`;
}

const response = await Functions.makeHttpRequest({ url: apiUrl });

if (response.error) return Functions.encodeString("NO");

const data = response.data;

// Simple heuristic: look for team name in results
const dataStr = JSON.stringify(data).toLowerCase();
const team = targetTeam.toLowerCase();

// Check if team won (their name appears near "winner" or score higher)
let yesWon = false;

if (data.events && Array.isArray(data.events)) {
  for (const event of data.events) {
    const eventStr = JSON.stringify(event).toLowerCase();
    if (team && !eventStr.includes(team)) continue;
    
    // Check competitions
    if (event.competitions) {
      for (const comp of event.competitions) {
        if (!comp.competitors) continue;
        for (const competitor of comp.competitors) {
          const cName = (competitor.team?.displayName || "").toLowerCase();
          if (team && !cName.includes(team)) continue;
          if (competitor.winner === true) {
            yesWon = true;
          }
        }
      }
    }
  }
}

// F1: check if driver/team won the last race
if (apiUrl.includes("ergast")) {
  const races = data?.MRData?.RaceTable?.Races;
  if (races && races.length > 0) {
    const lastRace = races[races.length - 1];
    const winner = lastRace?.Results?.[0]?.Driver;
    if (winner) {
      const winnerStr = `${winner.givenName} ${winner.familyName}`.toLowerCase();
      yesWon = winnerStr.includes(team) || team.includes(winnerStr);
    }
  }
}

return Functions.encodeString(yesWon ? "YES" : "NO");
