use regex::Regex;
use std::io;

use crate::board::{Board, Move};

const MIN: i32 = -99999;
const MAX: i32 = 99999;

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
        self.board.alpha_beta(5, MIN, MAX);
        if let Some(m) = self.board.best_move.last() {
            println!("bestmove {}{}", m.from.to_string(), m.to.to_string());
        } else {
            println!("nobestmove");
        }
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
        "fen rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1 moves b2e2 a9a8 b0c2 h7h0 i0h0 a8h8 h2h4 b7e7 a0b0 b9c7 b0b6 i9i7 b6c6 e7e8 c6c4 i7f7 e2h2 f7f0 e0f0",
    );
    // engine.position("startpos moves b0c2");
    let moves = engine.board.generate_move();
    println!("{:?}", moves);
    println!("{:?}", engine.board.chesses);
    engine.go();
    println!("{}", engine.board.counter)
}
