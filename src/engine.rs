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
                "go" => {
                    self.go(token.next().unwrap().split(" ").last().unwrap().parse().unwrap());
                }
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
    pub fn go(&mut self, depth: i32) {
        let (_, best_moves) = self.board.iterative_deepening(depth);
        if let Some(m) = best_moves.last() {
            if m.is_valid() {
                println!("bestmove {}{}", m.from.to_string(), m.to.to_string(),);
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
        "fen rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1 moves b2d2 b9a7 a9a8 h7h0 b0a2 a8d8 a0b0 d8d2 b0b7 d2h2 b7g7 h9g7 g3g4 i9h9",
    );
    // engine.position("startpos moves b0c2");
    engine.go(6);
    println!("{:?}", engine.board.chesses);
    println!("{} {}", engine.board.gen_counter, engine.board.counter);
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
    engine.go(8);
    println!("{} {}", engine.board.gen_counter, engine.board.counter);
}
