from pathlib import Path

path = Path(r"C:\Users\刘凯\PycharmProjects\shares\frontend\company\company.js")
text = path.read_text(encoding="utf-8")

old1 = """    const ratio = Number(item?.ratio);
    if (Number.isFinite(ratio)) {
      majorPct += ratio;
      majorCount += 1;
    }
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) majorShares += shares;
  }

  let fundPct = 0;
  let fundShares = 0;
  let fundCount = 0;
  let deduped = 0;
  const seenFunds = new Set();
  for (const item of funds) {
    const code = String(item?.code || \"\").trim().toLowerCase();
    const nameKey = normalizeHoldingsName(item?.name);
    const dedupeKey = code || nameKey;
    if (dedupeKey && seenFunds.has(dedupeKey)) {
      deduped += 1;
      continue;
    }
    if (dedupeKey) seenFunds.add(dedupeKey);
    const inTop =
      (code && topKeys.has(code)) || (nameKey && topKeys.has(nameKey));
    if (inTop) {
      deduped += 1;
      continue;
    }
    const ratio = fundRatioPct(item, totalShares);
    if (Number.isFinite(ratio)) {
      fundPct += ratio;
      fundCount += 1;
    }
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) fundShares += shares;
  }"""

# Fix escaping - the file uses normal quotes, not escaped
old1 = r"""    const ratio = Number(item?.ratio);
    if (Number.isFinite(ratio)) {
      majorPct += ratio;
      majorCount += 1;
    }
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) majorShares += shares;
  }

  let fundPct = 0;
  let fundShares = 0;
  let fundCount = 0;
  let deduped = 0;
  const seenFunds = new Set();
  for (const item of funds) {
    const code = String(item?.code || "").trim().toLowerCase();
    const nameKey = normalizeHoldingsName(item?.name);
    const dedupeKey = code || nameKey;
    if (dedupeKey && seenFunds.has(dedupeKey)) {
      deduped += 1;
      continue;
    }
    if (dedupeKey) seenFunds.add(dedupeKey);
    const inTop =
      (code && topKeys.has(code)) || (nameKey && topKeys.has(nameKey));
    if (inTop) {
      deduped += 1;
      continue;
    }
    const ratio = fundRatioPct(item, totalShares);
    if (Number.isFinite(ratio)) {
      fundPct += ratio;
      fundCount += 1;
    }
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) fundShares += shares;
  }"""

new1 = r"""    majorCount += 1;
    const ratio = Number(item?.ratio);
    if (Number.isFinite(ratio)) majorPct += ratio;
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) majorShares += shares;
  }

  let fundPct = 0;
  let fundShares = 0;
  let fundCount = 0;
  let deduped = 0;
  const seenFunds = new Set();
  for (const item of funds) {
    const code = String(item?.code || "").trim().toLowerCase();
    const nameKey = normalizeHoldingsName(item?.name);
    const dedupeKey = code || nameKey;
    if (dedupeKey && seenFunds.has(dedupeKey)) {
      deduped += 1;
      continue;
    }
    if (dedupeKey) seenFunds.add(dedupeKey);
    const inTop =
      (code && topKeys.has(code)) || (nameKey && topKeys.has(nameKey));
    if (inTop) {
      deduped += 1;
      continue;
    }
    fundCount += 1;
    const ratio = fundRatioPct(item, totalShares);
    if (Number.isFinite(ratio)) fundPct += ratio;
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) fundShares += shares;
  }"""

old2 = r"""      els.holdingsStatsLegend.innerHTML = rows
        .map((row) => {
          const sharesHint =
            row.shares != null && Number.isFinite(row.shares) && row.shares > 0
              ? `<small>${escapeHtml(fmtVol(row.shares))}股</small>`
              : row.detail
                ? `<small>${escapeHtml(row.detail)}</small>`
                : "";
          return `<li>
            <span class="holdings-stats-swatch" style="--swatch:${escapeHtml(row.color)}" aria-hidden="true"></span>
            <span class="holdings-stats-legend-label">${escapeHtml(row.label)}${sharesHint}</span>
            <span class="holdings-stats-legend-value">${escapeHtml(row.value)}</span>
          </li>`;
        })
        .join("");"""

new2 = r"""      els.holdingsStatsLegend.innerHTML = rows
        .map((row) => {
          const bits = [];
          if (row.detail) bits.push(row.detail);
          if (row.shares != null && Number.isFinite(row.shares) && row.shares > 0) {
            bits.push(`${fmtVol(row.shares)}股`);
          }
          const detail = bits.length
            ? `<small>${escapeHtml(bits.join(" · "))}</small>`
            : "";
          return `<li>
            <span class="holdings-stats-swatch" style="--swatch:${escapeHtml(row.color)}" aria-hidden="true"></span>
            <span class="holdings-stats-legend-label">${escapeHtml(row.label)}${detail}</span>
            <span class="holdings-stats-legend-value">${escapeHtml(row.value)}</span>
          </li>`;
        })
        .join("");"""

old3 = r"""  fundHoldersState.loading = true;
  fundHoldersState.error = "";
  paintFundHolders();
  if (els.refreshHoldersBtn) els.refreshHoldersBtn.disabled = true;"""

new3 = r"""  fundHoldersState.loading = true;
  fundHoldersState.error = "";
  paintFundHolders();
  paintHoldingsStats();
  if (els.refreshHoldersBtn) els.refreshHoldersBtn.disabled = true;"""

old4 = r"""  holdersState.loading = true;
  holdersState.error = "";
  paintHolders();
  if (els.refreshHoldersBtn) els.refreshHoldersBtn.disabled = true;"""

new4 = r"""  holdersState.loading = true;
  holdersState.error = "";
  paintHolders();
  paintHoldingsStats();
  if (els.refreshHoldersBtn) els.refreshHoldersBtn.disabled = true;"""

replacements = [
    ("OLD1", old1, new1),
    ("OLD2", old2, new2),
    ("OLD3", old3, new3),
    ("OLD4", old4, new4),
]

for name, old, new in replacements:
    if old not in text:
        print(f"{name} not found")
    else:
        text = text.replace(old, new, 1)
        print(f"{name} replaced")

path.write_text(text, encoding="utf-8")
print("done")
