function brawlerImageUrl(brawlerId) {
  return `https://cdn.brawlify.com/brawlers/borderless/${brawlerId}.png`;
}

function formatMode(mode) {
  const spaced = mode.replace(/([A-Z])/g, " $1");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function gamemodeIconUrl(mode, data) {
  return data.gamemode_icons[mode] || "";
}

function computeStarPlayerRanks(trioTags, starPlayerCounts) {
  const entries = trioTags.map(tag => ({
    tag: tag,
    count: starPlayerCounts[tag] || 0
  }));
  entries.sort((a, b) => b.count - a.count);

  const ranks = {};
  entries.forEach((entry, index) => {
    ranks[entry.tag] = index + 1;
  });
  return ranks;
}

async function loadState() {
  const response = await fetch("/api/state");
  const data = await response.json();

  if (!data.trio_tags || !data.profiles) {
    return;
  }

  const trioTags = data.trio_tags;
  const wins = data.wins;
  const losses = data.losses;

  document.getElementById("record").textContent = `${wins} / ${losses}`;

  const totalGames = wins + losses;
  if (totalGames > 0) {
    const winPct = Math.round((wins / totalGames) * 100);
    document.getElementById("winrate").textContent = `Winrate ${winPct}%`;
  } else {
    document.getElementById("winrate").textContent = `Winrate --`;
  }

  const ranks = computeStarPlayerRanks(trioTags, data.star_player_counts);

  trioTags.forEach((tag, index) => {
    const profile = data.profiles[tag];
    if (!profile) return;

    document.getElementById(`card-name-${index}`).textContent = profile.name;

    const isLastPlace = ranks[tag] === 3;
    const clownHtml = isLastPlace ? `<div class="clown-overlay">🤡</div>` : "";

    document.getElementById(`card-${index}`).innerHTML = `
      <div class="tooltip" id="tooltip-${index}">
        #${ranks[tag]} in Star Player · ${data.star_player_counts[tag] || 0} total
      </div>
      ${clownHtml}
      <img src="${brawlerImageUrl(profile.top_brawler_id)}" alt="${profile.top_brawler_name}">
    `;
  });

  renderHistory(data, trioTags);
}

function renderHistory(data, trioTags) {
  const recentMatches = (data.history || []).slice(-30).reverse();

  const container = document.getElementById("history-list");
  container.innerHTML = "";

  recentMatches.forEach(match => {
    const cellsHtml = trioTags.map(tag => {
      const brawler = match.brawlers[tag];
      const isStarPlayer = tag === match.star_player_tag;
      const starClass = isStarPlayer ? " star-player" : "";

      if (!brawler) {
        return `<div class="history-cell${starClass}">?</div>`;
      }
      return `<div class="history-cell${starClass}"><img src="${brawlerImageUrl(brawler.id)}" alt="${brawler.name}"></div>`;
    }).join("");

    const resultClass = match.result === "victory" ? "win" : "loss";

    const rowHtml = `
      <div class="history-row">
        <img class="mode-icon" src="${gamemodeIconUrl(match.mode, data)}" alt="${formatMode(match.mode)}">
        <div class="history-bar ${resultClass}">${cellsHtml}</div>
      </div>
    `;
    container.innerHTML += rowHtml;
  });
}

loadState();
setInterval(loadState, 15000);
