#![allow(dead_code)]

use engine::UCCIEngine;

mod board;
mod search;
mod zborist;
mod engine;
#[macro_use]
extern crate lazy_static;
fn main() {
    UCCIEngine::new().start();
}
