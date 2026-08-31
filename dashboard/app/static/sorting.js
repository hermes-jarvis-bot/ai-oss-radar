function sortWatchItems(items, sort = 'default') {
  const byName = (a, b) => String(a.full_name).localeCompare(String(b.full_name));
  const stars = item => Number.isFinite(item.stars) ? item.stars : null;
  const expiry = item => {
    if (!item.expires_at) return null;
    const timestamp = Date.parse(item.expires_at);
    return Number.isFinite(timestamp) ? timestamp : null;
  };
  const byStars = (a, b, direction) => {
    const aStars = stars(a); const bStars = stars(b);
    if (aStars == null && bStars == null) return byName(a, b);
    if (aStars == null) return 1;
    if (bStars == null) return -1;
    return direction * (aStars - bStars) || byName(a, b);
  };
  const byExpiry = (a, b, direction) => {
    const aExpiry = expiry(a); const bExpiry = expiry(b);
    if (aExpiry == null && bExpiry == null) return byName(a, b);
    if (aExpiry == null) return direction === 1 ? 1 : -1;
    if (bExpiry == null) return direction === 1 ? -1 : 1;
    return direction * (aExpiry - bExpiry) || byName(a, b);
  };
  const compare = (a, b) => {
    if (sort === 'stars-desc') return byStars(a, b, -1);
    if (sort === 'stars-asc') return byStars(a, b, 1);
    if (sort === 'expiry-soonest') return byExpiry(a, b, 1);
    if (sort === 'expiry-latest') return byExpiry(a, b, -1);
    return Number(b.manual) - Number(a.manual) || (a.manual ? byName(a, b) : byExpiry(a, b, 1));
  };
  const pinned = items.filter(item => item.manual).sort(compare);
  const automatic = items.filter(item => !item.manual).sort(compare);
  return [...pinned, ...automatic];
}

if (typeof module !== 'undefined') module.exports = { sortWatchItems };
