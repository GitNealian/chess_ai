use regex::Regex;
use std::io;

use crate::board::{Board, Move};

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
        println!("id copyright 2021-2022 www.nealian.com");
        println!("id author nealian");
        println!("id user 2021-2022 www.nealian.com");
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
        let (_, m) = self.board.minimax(4, self.board.turn, i32::MIN, i32::MAX);
        if let Some(m) = m.last() {
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
    // engine.position(
    //     "fen rnb1kabnr/4a4/1c5c1/p1p3p2/4N4/8p/P1P3P1P/2C4C1/9/RNBAKAB1R w - - 0 1 moves e5d7",
    // );
    engine.position(
        "start pos moves e5d7",
    );
    let moves = engine.board.generate_move();
    println!("{:?}", moves);
    println!("{:?}", engine.board.chesses);
    engine.go();
    println!("{}", engine.board.counter)
}
