/* Offline billing: a port of my_shop/parser.py plus the on-device catalogue and outbox.
   tests/test_parser.py checks the parser here still agrees with the Python one. */
(function (root, factory) {
	const api = factory();
	if (typeof module === "object" && module.exports) module.exports = api;
	else root.MyShopOffline = api;
})(typeof self !== "undefined" ? self : this, function () {
	const NUM_WORDS = new Map(Object.entries({
		one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7,
		eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13,
		fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18,
		nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50,
		sixty: 60, seventy: 70, eighty: 80, ninety: 90, hundred: 100,
		a: 1, an: 1,
		ek: 1, do: 2, teen: 3, tin: 3, char: 4, chaar: 4, panch: 5,
		paanch: 5, chhe: 6, che: 6, chah: 6, saat: 7, sat: 7, aath: 8,
		ath: 8, nau: 9, das: 10, dus: 10, gyarah: 11, barah: 12,
		terah: 13, chaudah: 14, pandrah: 15, solah: 16, satrah: 17,
		atharah: 18, unnis: 19, bees: 20, tees: 30, chalis: 40, pachas: 50,
		sau: 100,
		dozen: 12, darjan: 12,
	}));

	const STOPWORDS = new Set([
		"and", "aur", "plus", "then", "also", "add", "please", "ka", "ke", "ki",
		"or", "with", "the", "of", "chahiye", "dena", "de", "dedo", "bhi",
	]);

	const UNIT_WORDS = new Set([
		"kg", "kilo", "kilos", "kilogram", "gram", "grams", "gm", "piece", "pieces",
		"pcs", "pc", "nos", "no", "meter", "meters", "metre", "metres", "mtr", "feet",
		"foot", "ft", "inch", "inches", "packet", "packets", "pkt", "box", "boxes",
		"unit", "units", "set", "sets", "bundle", "bundles", "roll", "rolls",
		"m", "mm", "cm", "mtrs", "kgs", "litre", "litres", "ltr",
	]);

	const MATCH_THRESHOLD = 0.34;

	function normalise(text) {
		return (text || "").toLowerCase().replace(/[^a-z0-9\s.]/g, " ").replace(/\s+/g, " ").trim();
	}

	function asNumber(token) {
		if (/^[0-9]+$/.test(token)) return parseInt(token, 10);
		return NUM_WORDS.has(token) ? NUM_WORDS.get(token) : null;
	}

	function combine(previous, current) {
		if (previous >= 20 && previous % 10 === 0 && current < 10) return previous + current;
		return previous * current;
	}

	function parseTranscript(transcript) {
		const text = normalise(transcript);
		const tokens = text ? text.split(" ") : [];
		const segments = [];
		let qty = null;
		let words = [];

		function close() {
			let phrase = words.filter((w) => !STOPWORDS.has(w)).join(" ");
			for (;;) {
				const space = phrase.indexOf(" ");
				if (space > -1 && UNIT_WORDS.has(phrase.slice(0, space))) phrase = phrase.slice(space + 1);
				else break;
			}
			if (qty && phrase) segments.push({ qty, phrase });
		}

		for (const token of tokens) {
			const value = asNumber(token);
			if (value !== null) {
				if (qty !== null && !words.length) {
					qty = combine(qty, value);
					continue;
				}
				close();
				qty = value;
				words = [];
			} else if (!STOPWORDS.has(token)) {
				words.push(token);
			}
		}
		close();
		return segments;
	}

	/* difflib.SequenceMatcher(None, a, b).ratio(), including its autojunk rule */
	function ratio(a, b) {
		const b2j = new Map();
		for (let j = 0; j < b.length; j++) {
			if (!b2j.has(b[j])) b2j.set(b[j], []);
			b2j.get(b[j]).push(j);
		}
		if (b.length >= 200) {
			const ntest = Math.floor(b.length / 100) + 1;
			for (const [elt, idxs] of [...b2j]) if (idxs.length > ntest) b2j.delete(elt);
		}

		function longest(alo, ahi, blo, bhi) {
			let besti = alo, bestj = blo, bestsize = 0;
			let j2len = new Map();
			for (let i = alo; i < ahi; i++) {
				const next = new Map();
				for (const j of b2j.get(a[i]) || []) {
					if (j < blo) continue;
					if (j >= bhi) break;
					const k = (j2len.get(j - 1) || 0) + 1;
					next.set(j, k);
					if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; }
				}
				j2len = next;
			}
			while (besti > alo && bestj > blo && a[besti - 1] === b[bestj - 1]) { besti--; bestj--; bestsize++; }
			while (besti + bestsize < ahi && bestj + bestsize < bhi && a[besti + bestsize] === b[bestj + bestsize]) bestsize++;
			return [besti, bestj, bestsize];
		}

		let matched = 0;
		const queue = [[0, a.length, 0, b.length]];
		while (queue.length) {
			const [alo, ahi, blo, bhi] = queue.pop();
			const [i, j, k] = longest(alo, ahi, blo, bhi);
			if (!k) continue;
			matched += k;
			if (alo < i && blo < j) queue.push([alo, i, blo, j]);
			if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
		}
		const total = a.length + b.length;
		return total ? (2 * matched) / total : 1;
	}

	function score(phrase, candidate) {
		candidate = normalise(candidate);
		if (!candidate) return 0;
		const phraseTokens = new Set(phrase.split(" ").filter(Boolean));
		const candidateTokens = [...new Set(candidate.split(" "))];
		if (!phraseTokens.size) return 0;
		let hits = 0;
		for (const pt of phraseTokens) {
			if (candidateTokens.some((ct) => ct === pt || ct.startsWith(pt))) hits++;
		}
		return 0.7 * (hits / phraseTokens.size) + 0.3 * ratio(phrase, candidate);
	}

	function matchItem(phrase, items) {
		let best = null, bestScore = 0;
		for (const item of items) {
			const s = Math.max(score(phrase, item.item_name || ""), score(phrase, item.name || ""), score(phrase, item.description || ""));
			if (s > bestScore) { best = item; bestScore = s; }
		}
		if (bestScore < MATCH_THRESHOLD) return null;
		return { item_code: best.name, item_name: best.item_name, uom: best.stock_uom, score: Number(bestScore.toFixed(3)) };
	}

	function parseAndMatch(transcript, items) {
		const rows = [], unmatched = [];
		for (const segment of parseTranscript(transcript)) {
			const match = matchItem(segment.phrase, items);
			if (match) {
				const item = items.find((i) => i.name === match.item_code);
				rows.push({ ...match, qty: segment.qty, heard: segment.phrase, rate: item.rate || 0 });
			} else {
				unmatched.push(segment);
			}
		}
		return { rows, unmatched };
	}

	const DATA_KEY = "my_shop.offline_data";
	const OUTBOX_KEY = "my_shop.outbox";

	function read(key, fallback) {
		try {
			const value = localStorage.getItem(key);
			return value ? JSON.parse(value) : fallback;
		} catch (e) {
			return fallback;
		}
	}

	function write(key, value) {
		try {
			localStorage.setItem(key, JSON.stringify(value));
			return true;
		} catch (e) {
			return false;
		}
	}

	const outbox = {
		all: () => read(OUTBOX_KEY, []),
		add: (bill) => write(OUTBOX_KEY, outbox.all().concat([bill])),
		remove: (ref) => write(OUTBOX_KEY, outbox.all().filter((b) => b.client_ref !== ref)),
		update: (ref, patch) => write(OUTBOX_KEY, outbox.all().map((b) => (b.client_ref === ref ? { ...b, ...patch } : b))),
	};

	function localDate(date = new Date()) {
		const pad = (n) => String(n).padStart(2, "0");
		return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
	}

	function newRef() {
		if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
		return Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
	}

	function serverMessage(body) {
		try {
			return JSON.parse(body._server_messages || "[]").map((m) => JSON.parse(m).message).join("\n");
		} catch (e) {
			return "";
		}
	}

	/* Upload queued bills in order. Stops (keeping the queue) when the network or the
	   session is the problem; parks a bill with its error when the server refuses it. */
	async function flush(csrf) {
		const run = async () => {
			const result = { synced: 0, failed: 0, signin: false };
			for (const bill of outbox.all()) {
				if (bill.error) continue;
				let res;
				try {
					res = await fetch("/api/method/my_shop.api.create_invoice", {
						method: "POST",
						headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf },
						body: JSON.stringify(bill.args),
					});
				} catch (e) {
					break;
				}
				const body = await res.json().catch(() => ({}));
				if (res.ok) {
					outbox.remove(bill.client_ref);
					result.synced++;
				} else if (["CSRFTokenError", "PermissionError", "SessionExpired"].includes(body.exc_type) || res.status === 401 || res.status === 403) {
					result.signin = true;
					break;
				} else if (res.status >= 500 && !body.exc_type) {
					break;
				} else {
					outbox.update(bill.client_ref, { error: serverMessage(body) || body.exception || `Server said ${res.status}` });
					result.failed++;
				}
			}
			return result;
		};
		return typeof navigator !== "undefined" && navigator.locks ? navigator.locks.request("my_shop_sync", run) : run();
	}

	return {
		flush,
		parseTranscript,
		matchItem,
		parseAndMatch,
		saveData: (data) => write(DATA_KEY, data),
		loadData: () => read(DATA_KEY, null),
		outbox,
		localDate,
		newRef,
	};
});
