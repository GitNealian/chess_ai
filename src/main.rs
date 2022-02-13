#![allow(dead_code)]

use engine::UCCIEngine;

mod board;
mod engine;
mod zobrist;
#[macro_use]
extern crate lazy_static;
fn main() {
    UCCIEngine::new().start();
}
