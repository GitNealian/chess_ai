#[derive(Debug)]
pub struct Zobristable {
    hash_table: [[[u64; 7]; 90]; 2],
}

impl Zobristable {
    pub fn new() -> Self {
        let mut z = Zobristable {
            hash_table: [[[0u64; 7]; 90]; 2],
        };
        for l in 0..2 {
            for m in 0..90 {
                for n in 0..7 {
                    z.hash_table[l][m][n] = rand::random();
                }
            }
        }
        z
    }
}
