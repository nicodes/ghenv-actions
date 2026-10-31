// Synthetic credentials only. This probe implements the envelope contract
// independently of the exporter and never imports the ghenv provider crate.
use aws_lc_rs::{
    aead::{self, Aad, LessSafeKey, Nonce, UnboundKey},
    encoding::{AsDer, Pkcs8V1Der, PublicKeyX509Der},
    rand::{SecureRandom, SystemRandom},
    rsa::{KeySize, OAEP_SHA256_MGF1SHA256, OaepPrivateDecryptingKey, PrivateDecryptingKey},
};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde::Deserialize;
use serde_json::json;
use std::{
    collections::BTreeMap,
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::PathBuf,
};
use zeroize::Zeroizing;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn expected() -> BTreeMap<String, String> {
    BTreeMap::from([
        ("TOKEN".into(), "synthetic-only\n'quoted' $()=😀".into()),
        ("URL".into(), "http://127.0.0.1:3000".into()),
    ])
}
fn read(path: PathBuf, limit: u64) -> Result<Vec<u8>> {
    let mut data = Vec::new();
    fs::File::open(path)?
        .take(limit + 1)
        .read_to_end(&mut data)?;
    if data.len() as u64 > limit {
        return Err("oversized probe input".into());
    }
    Ok(data)
}
fn run() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 1 {
        return Err("expected prepare or verify".into());
    }
    let root = PathBuf::from(std::env::var("RUNNER_TEMP")?);
    let private_path = root.join("ghenv-synthetic-private.der");
    if args[0] == "prepare" {
        let private = PrivateDecryptingKey::generate(KeySize::Rsa3072)
            .map_err(|_| "key generation failed")?;
        let der =
            AsDer::<Pkcs8V1Der>::as_der(&private).map_err(|_| "private key encoding failed")?;
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        options.open(&private_path)?.write_all(der.as_ref())?;
        let public = AsDer::<PublicKeyX509Der>::as_der(&private.public_key())
            .map_err(|_| "public key encoding failed")?;
        let mut random = [0_u8; 16];
        SystemRandom::new()
            .fill(&mut random)
            .map_err(|_| "request ID generation failed")?;
        let request: String = random.iter().map(|byte| format!("{byte:02x}")).collect();
        let values = expected();
        let mut bundle = json!({"version":1,"environment":"Preview","repository":std::env::var("GITHUB_REPOSITORY")?,"secrets":{"TOKEN":values["TOKEN"],"UNREQUESTED":"must-stay-remote"},"variables":{"URL":values["URL"]}});
        let data = bundle.to_string();
        bundle["environment"] = "Production".into();
        let mut output = OpenOptions::new()
            .append(true)
            .open(std::env::var("GITHUB_OUTPUT")?)?;
        writeln!(
            output,
            "request-id={request}\npublic-key={}\nbundle={data}\nproduction-bundle={bundle}",
            STANDARD.encode(public.as_ref())
        )?;
        return Ok(());
    }
    if args[0] != "verify" {
        return Err("unknown probe command".into());
    }
    // This private key belongs only to the synthetic fixture, never the CLI.
    let der = Zeroizing::new(read(private_path.clone(), 8192)?);
    fs::remove_file(private_path)?;
    let private =
        PrivateDecryptingKey::from_pkcs8(&der).map_err(|_| "invalid fixture private key")?;
    let data = read(root.join("ghenv-downloaded/payload.json"), 4 << 20)?;
    #[derive(Deserialize)]
    struct Envelope {
        version: String,
        key: String,
        nonce: String,
        ciphertext: String,
    }
    let envelope: Envelope = serde_json::from_slice(&data)?;
    if envelope.version != "ghenv-v1" {
        return Err("unexpected protocol".into());
    }
    let private = OaepPrivateDecryptingKey::new(private).map_err(|_| "invalid RSA key")?;
    let mut buffer = Zeroizing::new(vec![0; private.min_output_size()]);
    let wrapped = STANDARD.decode(envelope.key)?;
    let key = private
        .decrypt(
            &OAEP_SHA256_MGF1SHA256,
            &wrapped,
            &mut buffer,
            Some(b"ghenv-v1"),
        )
        .map_err(|_| "key decryption failed")?;
    if key.len() != 32 {
        return Err("invalid payload key".into());
    }
    let cipher =
        LessSafeKey::new(UnboundKey::new(&aead::AES_256_GCM, key).map_err(|_| "invalid AES key")?);
    let nonce: [u8; 12] = STANDARD
        .decode(envelope.nonce)?
        .try_into()
        .map_err(|_| "invalid nonce")?;
    let mut ciphertext = Zeroizing::new(STANDARD.decode(envelope.ciphertext)?);
    let request = std::env::var("TEST_REQUEST_ID")?;
    let plaintext = cipher
        .open_in_place(
            Nonce::assume_unique_for_key(nonce),
            Aad::from(request.as_bytes()),
            &mut ciphertext,
        )
        .map_err(|_| "payload authentication failed")?;
    let values: BTreeMap<String, String> = serde_json::from_slice(plaintext)?;
    if values != expected() {
        return Err("unexpected exported values or unrequested entries".into());
    }
    println!("Synthetic encrypted round trip passed; only requested entries were exported");
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("probe: {error}");
        std::process::exit(1);
    }
}
