use regex::Regex;
use std::io;

use crate::{
    board::{Board, Move},
    constant::{MAX, MIN},
};

// UCCI引擎
pub struct UCCIEngine {
    pub board: Board,
}

impl UCCIEngine {
    pub fn new() -> Self {
        UCCIEngine {
            board: Board::init(),
        }
    }

    pub fn start(&mut self) {
        loop {
            let mut cmd = String::new();
            io::stdin().read_line(&mut cmd).unwrap();
            cmd = cmd.replace("\n", "");
            if cmd == "quit" {
                break;
            }
            let mut token = cmd.splitn(2, " ");
            let cmd = token.next().unwrap();
            match cmd {
                "ucci" => self.info(),
                "isready" => self.is_ready(),
                "position" => self.position(token.next().unwrap()),
                "go" => self.go(),
                _ => println!("not support"),
            }
        }
    }

    pub fn info(&self) {
        println!("id name nchess 1.0");
        println!("id copyright 2021-2022 www.nealian.cn");
        println!("id author nealian");
        println!("id user 2021-2022 www.nealian.cn");
        println!("option usemillisec type check");
        println!("ucciok");
    }

    pub fn is_ready(&self) {
        println!("readyok");
    }

    pub fn position(&mut self, param: &str) {
        let regex = Regex::new(
            r#"^(?:fen (?P<fen>[kabnrcpKABNRCP1-9/]+ [wrb] - - \d+ \d+)|(?P<startpos>startpos))(?: moves (?P<moves>[a-i]\d[a-i]\d(?: [a-i]\d[a-i]\d)*))?$"#,
        ).unwrap();
        for captures in regex.captures_iter(param) {
            if let Some(fen) = captures.name("fen") {
                self.board = Board::from_fen(fen.as_str());
            }
            if let Some(_) = captures.name("startpos") {
                self.board = Board::init();
            }
            if let Some(moves) = captures.name("moves") {
                for m in moves.as_str().split(" ") {
                    let (from, to) = m.split_at(2);
                    self.board.apply_move(&Move {
                        player: self.board.turn,
                        from: from.into(),
                        to: to.into(),
                        chess: self.board.chess_at(from.into()),
                        capture: self.board.chess_at(to.into()),
                    });
                }
            }
        }
    }
    pub fn go(&mut self) {
        let (_, best_moves) = self.board.alpha_beta(5, MIN, MAX);
        if let Some(m) = best_moves.last() {
            if m.is_valid() {
                println!(
                    "bestmove {}{}",
                    m.from.to_string(),
                    m.to.to_string(),
                );
                return;
            }
        }
        println!("nobestmove");
    }
    pub fn quit() {
        println!("bye");
    }
}
#[test]
fn test_ucci_engine() {
    let mut engine = UCCIEngine::new();
    engine.info();
    engine.is_ready();
    engine.position(
        "fen rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1 moves b2e2 a9a8 b0c2 h7h0 i0h0 a8h8 a0b0 i9i7 h2h4 i7e7 b0b6 g6g5 h4c4 h8h0 c4c9 d9e8 b6c6 h0g0 e2e6 h9g7 e6g6 g7e6 c6d6 e6f4 g6a6 f4h3 a6a9 h3g1 e0e1 g0f0 c3c4 g1f3 e1e2 b7b2 c2d4 e7d7 d6b6 f0e0 e2f2 e0f0 f2e2 f0e0 e2f2 e0f0 f2e2 f0e0 d0e1 f3g1 e2f2 d7f7 d4f3 g9e7 c9c6 e8d9 c6e6 f9e8 b6b9 e9f9 b9b2 e7c9 b2b5 f7f6 b5e5 e8d7 e6e7 f6f7 e7e6 f7f6 a9a6 f6f7 a6i6 f7f6 i6i9 c9e7 i9d9 f9f8 d9b9 f8f9 b9b6",
    );
    // engine.position("startpos moves b0c2");
    let moves = engine.board.generate_move();
    println!("{:?}", moves);
    println!("{:?}", engine.board.chesses);
    engine.go();
    println!("{}", engine.board.counter)
}

#[test]
fn test_kill() {
    let mut engine = UCCIEngine::new();
    engine.info();
    engine.is_ready();
    engine.position("fen 4k4/9/9/9/9/9/9/4p4/9/5K3 b - - 0 1");
    // engine.position("startpos moves b0c2");
    let moves = engine.board.generate_move();
    println!("{:?}", moves);
    println!("{:?}", engine.board.chesses);
    engine.go();
    println!("{}", engine.board.counter)
}
