use regex::{Captures, Regex};
use std::{
    cmp::Ordering,
    collections::HashMap,
    io::{self, BufRead},
    vec,
};

pub const BOARD_WIDTH: i32 = 9;
pub const BOARD_HEIGHT: i32 = 10;

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Chess {
    Black(ChessType),
    Red(ChessType),
    None,
}

impl Chess {
    pub fn value(&self) -> i32 {
        if let Some(ct) = self.chess_type() {
            ct.value()
        } else {
            0x0
        }
    }
    pub fn belong_to(&self, player: Player) -> bool {
        if let Chess::Black(_) = self {
            player == Player::Black
        } else if let Chess::Red(_) = self {
            player == Player::Red
        } else {
            false
        }
    }
    pub fn chess_type(&self) -> Option<ChessType> {
        match self {
            Chess::Black(ct) => Some(ct.to_owned()),
            Chess::Red(ct) => Some(ct.to_owned()),
            Chess::None => None,
        }
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum ChessType {
    King,    // 帅
    Advisor, // 士
    Bishop,  // 相
    Knight,  // 马
    Rook,    // 车
    Cannon,  // 炮
    Pawn,    // 兵
}

impl ChessType {
    pub fn value(&self) -> i32 {
        match self {
            ChessType::King => 5,
            ChessType::Advisor => 1,
            ChessType::Bishop => 1,
            ChessType::Knight => 3,
            ChessType::Rook => 4,
            ChessType::Cannon => 3,
            ChessType::Pawn => 2,
        }
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Player {
    Red,
    Black,
}

impl Player {
    fn next(&self) -> Player {
        if self == &Player::Red {
            Player::Black
        } else {
            Player::Red
        }
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub struct Position {
    row: i32,
    col: i32,
}

impl Position {
    pub fn new(row: i32, col: i32) -> Self {
        Position { row, col }
    }
    pub fn up(&self, delta: i32) -> Self {
        Position::new(self.row - delta, self.col)
    }
    pub fn down(&self, delta: i32) -> Self {
        Position::new(self.row + delta, self.col)
    }
    pub fn left(&self, delta: i32) -> Self {
        Position::new(self.row, self.col - delta)
    }
    pub fn right(&self, delta: i32) -> Self {
        Position::new(self.row, self.col + delta)
    }
    pub fn flip(&self) -> Self {
        Position::new(BOARD_HEIGHT - 1 - self.row, BOARD_WIDTH - 1 - self.col)
    }
}

#[derive(Debug)]
pub struct Move {
    pub player: Player, // 玩家
    pub from: Position, // 起手位置
    pub to: Position,   // 落子位置
    pub chess: Chess,   // 记录一下运的子，如果后面没用到就删了
    pub capture: Chess, // 这一步吃的子
}
impl Move {
    pub fn with_target(&self, to: Position, capture: Chess) -> Move {
        Move {
            player: self.player,
            from: self.from,
            to,
            chess: self.chess,
            capture,
        }
    }
}
impl From<&str> for Position {
    fn from(m: &str) -> Self {
        let mb = m.as_bytes();
        Position::new(
            BOARD_HEIGHT - 1 - (mb[1] - '0' as u8) as i32,
            (mb[0] - 'a' as u8) as i32,
        )
    }
}
impl ToString for Position {
    fn to_string(&self) -> String {
        format!(
            "{}{}",
            char::from_u32((self.col as u8 + 'a' as u8) as u32).unwrap(),
            char::from_u32(((BOARD_HEIGHT as u8 - 1 - self.row as u8) + '0' as u8) as u32).unwrap()
        )
    }
}

#[derive(Clone)]
pub struct Board {
    // 9×10的棋盘，红方在下，黑方在上
    pub chesses: [[Chess; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize],
    pub turn: Player,
    pub counter: i32,
}

// 棋子是否在棋盘内
pub fn in_board(pos: Position) -> bool {
    pos.row >= 0 && pos.row < BOARD_HEIGHT && pos.col >= 0 && pos.col < BOARD_WIDTH
}

// 棋子是否在玩家的楚河汉界以内
pub fn in_country(row: i32, player: Player) -> bool {
    let base_row = if player == Player::Red {
        BOARD_HEIGHT - 1
    } else {
        0
    };
    (row - base_row).abs() < BOARD_HEIGHT / 2
}

// 棋子是否在九宫格内
pub fn in_palace(pos: Position, player: Player) -> bool {
    if player == Player::Black {
        pos.row >= 0 && pos.row < 3 && pos.col >= 3 && pos.col < 6
    } else {
        pos.row >= 7 && pos.row < BOARD_HEIGHT && pos.col >= 3 && pos.col < 6
    }
}

const KING_VALUE_TABLE: [[i32; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize] = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 1, 0, 0, 0],
    [0, 0, 0, 2, 2, 2, 0, 0, 0],
    [0, 0, 0, 11, 15, 11, 0, 0, 0],
];

const ADVISOR_VALUE_TABLE: [[i32; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize] = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 20, 0, 20, 0, 0, 0],
    [0, 0, 0, 0, 23, 0, 0, 0, 0],
    [0, 0, 0, 20, 0, 20, 0, 0, 0],
];

const BISHOP_VALUE_TABLE: [[i32; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize] = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 20, 0, 0, 0, 20, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [18, 0, 0, 0, 23, 0, 0, 0, 18],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 20, 0, 0, 0, 20, 0, 0],
];

const ROOK_VALUE_TABLE: [[i32; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize] = [
    [206, 208, 207, 213, 214, 213, 207, 208, 206],
    [206, 212, 209, 216, 233, 216, 209, 212, 206],
    [206, 208, 207, 214, 216, 214, 207, 208, 206],
    [206, 213, 213, 216, 216, 216, 213, 213, 206],
    [208, 211, 211, 214, 215, 214, 211, 211, 208],
    [208, 212, 212, 214, 215, 214, 212, 212, 208],
    [204, 209, 204, 212, 214, 212, 204, 209, 204],
    [198, 208, 204, 212, 212, 212, 204, 208, 198],
    [200, 208, 206, 212, 200, 212, 206, 208, 200],
    [194, 206, 204, 212, 200, 212, 204, 206, 194],
];

const KNIGHT_VALUE_TABLE: [[i32; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize] = [
    [90, 90, 90, 96, 90, 96, 90, 90, 90],
    [90, 96, 103, 97, 94, 97, 103, 96, 90],
    [92, 98, 99, 103, 99, 103, 99, 98, 92],
    [93, 108, 100, 107, 100, 107, 100, 108, 93],
    [90, 100, 99, 103, 104, 103, 99, 100, 90],
    [90, 98, 101, 102, 103, 102, 101, 98, 90],
    [92, 94, 98, 95, 98, 95, 98, 94, 92],
    [93, 92, 94, 95, 92, 95, 94, 92, 93],
    [85, 90, 92, 93, 78, 93, 92, 90, 85],
    [88, 85, 90, 88, 90, 88, 90, 85, 88],
];

const CANNON_VALUE_TABLE: [[i32; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize] = [
    [100, 100, 96, 91, 90, 91, 96, 100, 100],
    [98, 98, 96, 92, 89, 92, 96, 98, 98],
    [97, 97, 96, 91, 92, 91, 96, 97, 97],
    [96, 99, 99, 98, 100, 98, 99, 99, 96],
    [96, 96, 96, 96, 100, 96, 96, 96, 96],
    [95, 96, 99, 96, 100, 96, 99, 96, 95],
    [96, 96, 96, 96, 96, 96, 96, 96, 96],
    [97, 96, 100, 99, 101, 99, 100, 96, 97],
    [96, 97, 98, 98, 98, 98, 98, 97, 96],
    [96, 96, 97, 99, 99, 99, 97, 96, 96],
];

const PAWN_VALUE_TABLE: [[i32; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize] = [
    [9, 9, 9, 11, 13, 11, 9, 9, 9],
    [19, 24, 34, 42, 44, 42, 34, 24, 19],
    [19, 24, 32, 37, 37, 37, 32, 24, 19],
    [19, 23, 27, 29, 30, 29, 27, 23, 19],
    [14, 18, 20, 27, 29, 27, 20, 18, 14],
    [7, 0, 13, 0, 16, 0, 13, 0, 7],
    [7, 0, 7, 0, 15, 0, 7, 0, 7],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
];

const INITIATIVE_BONUS: i32 = 3;
lazy_static! {
    static ref FEN_MAP: HashMap<char, Chess> = HashMap::from([
        ('k', Chess::Black(ChessType::King)),
        ('a', Chess::Black(ChessType::Advisor)),
        ('b', Chess::Black(ChessType::Bishop)),
        ('n', Chess::Black(ChessType::Knight)),
        ('r', Chess::Black(ChessType::Rook)),
        ('c', Chess::Black(ChessType::Cannon)),
        ('p', Chess::Black(ChessType::Pawn)),
        ('K', Chess::Red(ChessType::King)),
        ('A', Chess::Red(ChessType::Advisor)),
        ('B', Chess::Red(ChessType::Bishop)),
        ('N', Chess::Red(ChessType::Knight)),
        ('R', Chess::Red(ChessType::Rook)),
        ('C', Chess::Red(ChessType::Cannon)),
        ('P', Chess::Red(ChessType::Pawn)),
    ]);
}

impl Board {
    pub fn init() -> Self {
        Board {
            chesses: [
                [
                    Chess::Black(ChessType::Rook),
                    Chess::Black(ChessType::Knight),
                    Chess::Black(ChessType::Bishop),
                    Chess::Black(ChessType::Advisor),
                    Chess::Black(ChessType::King),
                    Chess::Black(ChessType::Advisor),
                    Chess::Black(ChessType::Bishop),
                    Chess::Black(ChessType::Knight),
                    Chess::Black(ChessType::Rook),
                ],
                [
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                ],
                [
                    Chess::None,
                    Chess::Black(ChessType::Cannon),
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::Black(ChessType::Cannon),
                    Chess::None,
                ],
                [
                    Chess::Black(ChessType::Pawn),
                    Chess::None,
                    Chess::Black(ChessType::Pawn),
                    Chess::None,
                    Chess::Black(ChessType::Pawn),
                    Chess::None,
                    Chess::Black(ChessType::Pawn),
                    Chess::None,
                    Chess::Black(ChessType::Pawn),
                ],
                [
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                ],
                [
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                ],
                [
                    Chess::Red(ChessType::Pawn),
                    Chess::None,
                    Chess::Red(ChessType::Pawn),
                    Chess::None,
                    Chess::Red(ChessType::Pawn),
                    Chess::None,
                    Chess::Red(ChessType::Pawn),
                    Chess::None,
                    Chess::Red(ChessType::Pawn),
                ],
                [
                    Chess::None,
                    Chess::Red(ChessType::Cannon),
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::Red(ChessType::Cannon),
                    Chess::None,
                ],
                [
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                    Chess::None,
                ],
                [
                    Chess::Red(ChessType::Rook),
                    Chess::Red(ChessType::Knight),
                    Chess::Red(ChessType::Bishop),
                    Chess::Red(ChessType::Advisor),
                    Chess::Red(ChessType::King),
                    Chess::Red(ChessType::Advisor),
                    Chess::Red(ChessType::Bishop),
                    Chess::Red(ChessType::Knight),
                    Chess::Red(ChessType::Rook),
                ],
            ],
            turn: Player::Red,
            counter: 0,
        }
    }
    pub fn empty() -> Self {
        Board {
            chesses: [[Chess::None; BOARD_WIDTH as usize]; BOARD_HEIGHT as usize],
            turn: Player::Red,
            counter: 0,
        }
    }
    pub fn from_fen(fen: &str) -> Self {
        let mut board = Board::empty();
        let mut parts = fen.split(" ");
        let pos = parts.next().unwrap();
        let mut i = 0;
        for row in pos.split("/") {
            let mut j = 0;
            for col in row.chars() {
                if col.is_numeric() {
                    j += col.to_digit(10).unwrap() as i32;
                } else {
                    if let Some(chess) = FEN_MAP.get(&col) {
                        board.set_chess(Position::new(i, j), chess.to_owned());
                    }
                    j += 1;
                }
            }
            i += 1;
        }
        let turn = parts.next().unwrap();
        if turn == "b" {
            board.turn = Player::Black;
        }
        board
    }
    pub fn apply_move(&mut self, m: &Move) {
        let chess = self.chess_at(m.from);
        self.set_chess(m.to, chess);
        self.set_chess(m.from, Chess::None);
        self.turn = m.player.next();
    }
    pub fn undo_move(&mut self, m: &Move) {
        let chess = self.chess_at(m.to);
        self.set_chess(m.from, chess);
        self.set_chess(m.to, m.capture);
        self.turn = m.player.next();
    }
    pub fn chess_at(&self, pos: Position) -> Chess {
        if in_board(pos) {
            self.chesses[pos.row as usize][pos.col as usize]
        } else {
            Chess::None
        }
    }
    pub fn set_chess(&mut self, pos: Position, chess: Chess) {
        self.chesses[pos.row as usize][pos.col as usize] = chess;
    }
    pub fn has_chess_between(&self, posa: Position, posb: Position) -> bool {
        if posa.row == posb.row {
            for j in posa.col.min(posb.col) + 1..posb.col.max(posa.col) {
                if self
                    .chess_at(Position::new(posa.row, j))
                    .chess_type()
                    .is_some()
                {
                    return true;
                }
            }
        } else if posa.col == posb.col {
            for i in posa.row.min(posb.row) + 1..posb.row.max(posa.row) {
                if self
                    .chess_at(Position::new(i, posa.col))
                    .chess_type()
                    .is_some()
                {
                    return true;
                }
            }
        }
        return false;
    }
    pub fn king_position(&self, player: Player) -> Option<Position> {
        if player == Player::Black {
            for i in 0..3 {
                for j in 3..6 {
                    if self.chess_at(Position::new(i, j)) == Chess::Black(ChessType::King) {
                        return Some(Position::new(i, j));
                    }
                }
            }
        } else {
            for i in 7..10 {
                for j in 3..6 {
                    if self.chess_at(Position::new(i, j)) == Chess::Red(ChessType::King) {
                        return Some(Position::new(i, j));
                    }
                }
            }
        }
        None
    }
    pub fn king_eye_to_eye(&self) -> bool {
        !self.has_chess_between(
            self.king_position(Player::Red).unwrap(),
            self.king_position(Player::Black).unwrap(),
        )
    }
    pub fn is_checked(&self) -> bool {
        let moves = self.generate_move();
        moves.iter().any(|x| {
            x.capture
                .chess_type()
                .map_or(false, |ct| ct == ChessType::King)
        }) || self.king_eye_to_eye()
    }
    pub fn generate_move(&self) -> Vec<Move> {
        let mut moves = vec![];
        for i in 0..BOARD_HEIGHT {
            for j in 0..BOARD_WIDTH {
                let position_base = Position::new(i, j);
                // 遍历每个行棋方的棋
                let chess = self.chess_at(position_base);
                if chess.belong_to(self.turn) {
                    if let Some(ct) = chess.chess_type() {
                        let mut targets = vec![];
                        match ct {
                            ChessType::King => {
                                targets.append(&mut vec![
                                    position_base.up(1),
                                    position_base.down(1),
                                    position_base.left(1),
                                    position_base.right(1),
                                ]);
                            }
                            ChessType::Advisor => {
                                targets.append(&mut vec![
                                    position_base.up(1).left(1),
                                    position_base.up(1).right(1),
                                    position_base.down(1).left(1),
                                    position_base.down(1).right(1),
                                ]);
                            }
                            ChessType::Bishop => {
                                if self.chess_at(position_base.up(1).left(1)) == Chess::None {
                                    targets.push(position_base.up(2).left(2));
                                }
                                if self.chess_at(position_base.up(1).right(1)) == Chess::None {
                                    targets.push(position_base.up(2).right(2));
                                }
                                if self.chess_at(position_base.down(1).left(1)) == Chess::None {
                                    targets.push(position_base.down(2).left(2));
                                }
                                if self.chess_at(position_base.down(1).right(1)) == Chess::None {
                                    targets.push(position_base.down(2).right(2));
                                }
                            }
                            ChessType::Knight => {
                                if self.chess_at(position_base.up(1)) == Chess::None {
                                    targets.push(position_base.up(2).left(1));
                                    targets.push(position_base.up(2).right(1));
                                }
                                if self.chess_at(position_base.down(1)) == Chess::None {
                                    targets.push(position_base.down(2).left(1));
                                    targets.push(position_base.down(2).right(1));
                                }
                                if self.chess_at(position_base.left(1)) == Chess::None {
                                    targets.push(position_base.up(1).left(2));
                                    targets.push(position_base.down(1).left(2));
                                }
                                if self.chess_at(position_base.right(1)) == Chess::None {
                                    targets.push(position_base.up(1).right(2));
                                    targets.push(position_base.down(1).right(2));
                                }
                            }
                            ChessType::Rook => {
                                for delta in 1..(j + 1) {
                                    targets.push(position_base.left(delta));
                                    if self.chess_at(position_base.left(delta)) != Chess::None {
                                        break;
                                    }
                                }
                                for delta in 1..(BOARD_WIDTH - j) {
                                    targets.push(position_base.right(delta));
                                    if self.chess_at(position_base.right(delta)) != Chess::None {
                                        break;
                                    }
                                }
                                for delta in 1..(i + 1) {
                                    targets.push(position_base.up(delta));
                                    if self.chess_at(position_base.up(delta)) != Chess::None {
                                        break;
                                    }
                                }
                                for delta in 1..(BOARD_HEIGHT - i) {
                                    targets.push(position_base.down(delta));
                                    if self.chess_at(position_base.down(delta)) != Chess::None {
                                        break;
                                    }
                                }
                            }
                            ChessType::Cannon => {
                                let mut has_chess = false;
                                for delta in 1..(j + 1) {
                                    if !has_chess {
                                        if self.chess_at(position_base.left(delta)) != Chess::None {
                                            has_chess = true;
                                        } else {
                                            targets.push(position_base.left(delta));
                                        }
                                    } else if self.chess_at(position_base.left(delta))
                                        != Chess::None
                                    {
                                        targets.push(position_base.left(delta));
                                        break;
                                    }
                                }
                                let mut has_chess = false;
                                for delta in 1..(BOARD_WIDTH - j) {
                                    if !has_chess {
                                        if self.chess_at(position_base.right(delta)) != Chess::None
                                        {
                                            has_chess = true;
                                        } else {
                                            targets.push(position_base.right(delta));
                                        }
                                    } else if self.chess_at(position_base.right(delta))
                                        != Chess::None
                                    {
                                        targets.push(position_base.right(delta));
                                        break;
                                    }
                                }
                                let mut has_chess = false;
                                for delta in 1..(i + 1) {
                                    if !has_chess {
                                        if self.chess_at(position_base.up(delta)) != Chess::None {
                                            has_chess = true;
                                        } else {
                                            targets.push(position_base.up(delta));
                                        }
                                    } else if self.chess_at(position_base.up(delta)) != Chess::None
                                    {
                                        targets.push(position_base.up(delta));
                                        break;
                                    }
                                }
                                let mut has_chess = false;
                                for delta in 1..(BOARD_HEIGHT - i) {
                                    if !has_chess {
                                        if self.chess_at(position_base.down(delta)) != Chess::None {
                                            has_chess = true;
                                        } else {
                                            targets.push(position_base.down(delta));
                                        }
                                    } else if self.chess_at(position_base.down(delta))
                                        != Chess::None
                                    {
                                        targets.push(position_base.down(delta));
                                        break;
                                    }
                                }
                            }
                            ChessType::Pawn => {
                                if self.turn == Player::Black {
                                    targets.push(position_base.down(1))
                                } else {
                                    targets.push(position_base.up(1));
                                }
                                // 过河兵可以左右走
                                if !in_country(i as i32, self.turn) {
                                    targets.push(position_base.left(1));
                                    targets.push(position_base.right(1));
                                }
                            }
                        }
                        let move_base = Move {
                            player: self.turn,
                            from: position_base,
                            to: position_base,
                            chess,
                            capture: Chess::None,
                        };
                        for target in targets {
                            let valid = if ct == ChessType::King || ct == ChessType::Advisor {
                                // 帅和士要在九宫格内
                                in_palace(target, self.turn)
                            } else if ct == ChessType::Bishop {
                                // 象不能过河
                                in_country(target.row, self.turn) && in_board(target)
                            } else {
                                in_board(target)
                            };

                            if valid {
                                if !self.chess_at(target).belong_to(self.turn) {
                                    moves
                                        .push(move_base.with_target(target, self.chess_at(target)));
                                }
                            }
                        }
                    }
                }
            }
        }
        moves.sort_by(|a, b| {
            ((self.chess_at(a.to).value() << 3) - self.chess_at(a.from).value())
                .cmp(&((self.chess_at(b.to).value() << 3) - self.chess_at(b.from).value()))
        });
        moves
    }
    // 简单的评价，双方每个棋子的子力之和的差
    pub fn evaluate(&self, player: Player) -> i32 {
        let mut red_score = 0;
        let mut black_score = 0;
        for i in 0..BOARD_HEIGHT as usize {
            for j in 0..BOARD_WIDTH as usize {
                let chess = self.chess_at(Position::new(i as i32, j as i32));
                if let Some(ct) = chess.chess_type() {
                    let pos = if chess.belong_to(Player::Black) {
                        Position::new(i as i32, j as i32).flip()
                    } else {
                        Position::new(i as i32, j as i32)
                    };
                    let score = match ct {
                        ChessType::King => KING_VALUE_TABLE[pos.row as usize][pos.col as usize],
                        ChessType::Advisor => {
                            ADVISOR_VALUE_TABLE[pos.row as usize][pos.col as usize]
                        }
                        ChessType::Bishop => BISHOP_VALUE_TABLE[pos.row as usize][pos.col as usize],
                        ChessType::Knight => KNIGHT_VALUE_TABLE[pos.row as usize][pos.col as usize],
                        ChessType::Rook => ROOK_VALUE_TABLE[pos.row as usize][pos.col as usize],
                        ChessType::Cannon => CANNON_VALUE_TABLE[pos.row as usize][pos.col as usize],
                        ChessType::Pawn => PAWN_VALUE_TABLE[pos.row as usize][pos.col as usize],
                    };
                    if chess.belong_to(Player::Black) {
                        black_score += score
                    } else {
                        red_score += score
                    }
                }
            }
        }
        if player == Player::Red {
            red_score - black_score + INITIATIVE_BONUS
        } else {
            black_score - red_score + INITIATIVE_BONUS
        }
    }
    pub fn minimax(
        &mut self,
        depth: i32,
        player: Player,
        mut alpha: i32,
        mut beta: i32,
    ) -> (i32, Vec<Move>) {
        if depth == 0 {
            self.counter += 1;
            return (self.evaluate(player), vec![]);
        }
        // 已方，最大值
        if self.turn == player {
            let mut best_value = i32::MIN;
            let mut best_move: Vec<Move> = vec![];
            for m in self.generate_move() {
                self.apply_move(&m);
                if self.is_checked() {
                    self.undo_move(&m);
                    continue;
                }
                let (v, mut mn) = self.minimax(depth - 1, player, alpha, beta);
                self.undo_move(&m);
                if best_value <= v {
                    best_value = v;
                    mn.push(m);
                    best_move = mn;
                    beta = beta.max(best_value);
                }
                if beta <= alpha {
                    break;
                }
            }
            return (best_value, best_move);
        } else {
            // 对方，最小值
            let mut best_value = i32::MAX;
            let mut best_move: Vec<Move> = vec![];
            for m in self.generate_move() {
                self.apply_move(&m);
                if self.is_checked() {
                    self.undo_move(&m);
                    continue;
                }
                let (v, mut mn) = self.minimax(depth - 1, player, alpha, beta);
                self.undo_move(&m);
                if best_value >= v {
                    best_value = v;
                    mn.push(m);
                    best_move = mn;
                    alpha = alpha.min(best_value);
                }
                if beta <= alpha {
                    break;
                }
            }
            return (best_value, best_move);
        }
    }
}

#[test]
fn test_generate_move() {
    assert_eq!(
        Board::init().generate_move().len(),
        5 + 24 + 4 + 4 + 4 + 2 + 1
    );
}

#[test]
fn test_evaluate() {
    let mut board = Board::init();
    board.apply_move(&Move {
        player: Player::Red,
        from: Position { row: 9, col: 8 },
        to: Position { row: 7, col: 8 },
        chess: Chess::Red(ChessType::Rook),
        capture: Chess::None,
    });
    assert_eq!(board.evaluate(Player::Red), 7);
}

#[test]
fn test_minimax() {
    println!(
        "{:?}",
        Board::init().minimax(1, Player::Red, i32::MIN, i32::MAX)
    ); // 炮吃马
    println!(
        "{:?}",
        Board::init().minimax(2, Player::Red, i32::MIN, i32::MAX)
    ); // 炮吃马
    println!(
        "{:?}",
        Board::init().minimax(3, Player::Red, i32::MIN, i32::MAX)
    ); // 炮吃马
    println!(
        "{:?}",
        Board::init().minimax(4, Player::Red, i32::MIN, i32::MAX)
    ); // 跳马
       // let mut board = Board::init();
       // let rst = board.minimax(5, Player::Red, i32::MIN, i32::MAX);
       // let counter = board.counter;
       // println!("{} \n {:?}", counter, rst); // 跳马
       //                                       /* */
       // println!(
       //     "{:?}",
       //     Board::init().minimax(6, Player::Red, i32::MIN, i32::MAX)
       // ); // 跳马
}

#[test]
fn test_from_fen() {
    let fen = "rnb1kabnr/4a4/1c5c1/p1p3p2/4N4/8p/P1P3P1P/2C4C1/9/RNBAKAB1R w - - 0 1 moves e5d7";
    println!("{:?}", Board::from_fen(fen).chesses);
}

#[test]
fn test_king_eye_to_eye() {
    let board = Board::from_fen("rnbakabnr/9/1c5c1/9/9/9/9/1C5C1/9/RNBAKABNR w - - 0 1");
    println!("{:?}", board.chesses);
    println!("{}", board.king_eye_to_eye());
    let board = Board::init();
    println!("{}", board.king_eye_to_eye());
}
