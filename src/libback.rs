// use board::Board;
// use board::Move;
// use constant::MIN;
// use constant::MAX;
// use regex::Regex;
// use wasm_bindgen::prelude::*;

// use engine::UCCIEngine;
// mod board;
// mod constant;
// mod engine;
// mod zobrist;
// #[macro_use]
// extern crate lazy_static;

// #[wasm_bindgen]
// pub fn search(position: &str, depth: i32)-> String {
//     let mut board = Board::init();
//     let regex = Regex::new(
//         r#"^(?:fen (?P<fen>[kabnrcpKABNRCP1-9/]+ [wrb] - - \d+ \d+)|(?P<startpos>startpos))(?: moves (?P<moves>[a-i]\d[a-i]\d(?: [a-i]\d[a-i]\d)*))?$"#,
//     ).unwrap();
//     for captures in regex.captures_iter(position) {
//         if let Some(fen) = captures.name("fen") {
//             board = Board::from_fen(fen.as_str());
//         }
//         if let Some(_) = captures.name("startpos") {
//             board = Board::init();
//         }
//         if let Some(moves) = captures.name("moves") {
//             for m in moves.as_str().split(" ") {
//                 let (from, to) = m.split_at(2);
//                 board.apply_move(&Move {
//                     player: board.turn,
//                     from: from.into(),
//                     to: to.into(),
//                     chess: board.chess_at(from.into()),
//                     capture: board.chess_at(to.into()),
//                 });
//             }
//         }
//     }
//     format!("{:?}", board.alpha_beta_pvs(depth, MIN, MAX))
// }
