#![allow(dead_code)]

use engine::UCCIEngine;

mod constant;
mod board;
mod engine;
mod zobrist;
#[macro_use]
extern crate lazy_static;
fn main() {
    UCCIEngine::new(Some("/home/nealian/desktop_new/chess/chess_ai/BOOK.DAT")).start();
}
