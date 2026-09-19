export const LABELS = {
  "red-K": "帅", "red-A": "仕", "red-B": "相", "red-N": "马",
  "red-R": "车", "red-C": "炮", "red-P": "兵",
  "black-K": "将", "black-A": "士", "black-B": "象", "black-N": "马",
  "black-R": "车", "black-C": "炮", "black-P": "卒",
};

export function fenToPieces(fen) {
  const rows = fen.split(" ")[0].split("/");
  const pieces = [];
  rows.forEach((row, rowIndex) => {
    const y = 9 - rowIndex;
    let x = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) {
        x += Number(ch);
      } else {
        const side = ch === ch.toUpperCase() ? "red" : "black";
        const kind = ch.toUpperCase();
        pieces.push({ x, y, side, kind, label: LABELS[`${side}-${kind}`] });
        x += 1;
      }
    }
  });
  return pieces;
}

export function applyMove(pieces, move) {
  const moving = pieces.find((p) => p.x === move.x1 && p.y === move.y1);
  const next = pieces.filter(
    (p) => !(p.x === move.x2 && p.y === move.y2) && !(p.x === move.x1 && p.y === move.y1)
  );
  if (moving) next.push({ ...moving, x: move.x2, y: move.y2 });
  return next;
}
