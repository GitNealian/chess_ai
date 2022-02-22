use std::collections::HashMap;

use crate::{zobrist::Zobristable, board::{Chess, ChessType}};

pub const MIN: i32 = -99999;
pub const KILL: i32 = MIN + 100;
pub const MAX: i32 = 99999;
pub const RECORD_SIZE: i32 = 0x1FFFFE;
pub const MAX_DEPTH: i32 = 64;

lazy_static! {
    pub static ref FEN_MAP: HashMap<char, Chess> = HashMap::from([
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
    pub static ref ZOBRIST_TABLE: Zobristable = Zobristable::new();
    pub static ref ZOBRIST_TABLE_LOCK: Zobristable = Zobristable::new();
}
