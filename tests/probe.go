// This fixture uses synthetic credentials only. It verifies interoperability
// independently of the exporter implementation pinned by the action.
package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
)

var expected = map[string]string{"TOKEN": "synthetic-only\n'quoted' $()=😀", "URL": "http://127.0.0.1:3000"}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "probe:", err)
		os.Exit(1)
	}
}

func run() error {
	if len(os.Args) != 2 {
		return fmt.Errorf("expected prepare or verify")
	}
	privatePath := filepath.Join(os.Getenv("RUNNER_TEMP"), "ghenv-synthetic-private.der")
	if os.Args[1] == "prepare" {
		key, err := rsa.GenerateKey(rand.Reader, 3072)
		if err != nil {
			return err
		}
		if err := os.WriteFile(privatePath, x509.MarshalPKCS1PrivateKey(key), 0600); err != nil {
			return err
		}
		der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
		if err != nil {
			return err
		}
		id := make([]byte, 16)
		if _, err := rand.Read(id); err != nil {
			return err
		}
		bundle := map[string]any{"version": 1, "environment": "Preview", "repository": os.Getenv("GITHUB_REPOSITORY"),
			"secrets":   map[string]string{"TOKEN": expected["TOKEN"], "UNREQUESTED": "must-stay-remote"},
			"variables": map[string]string{"URL": expected["URL"]}}
		data, err := json.Marshal(bundle)
		if err != nil {
			return err
		}
		bundle["environment"] = "Production"
		bad, err := json.Marshal(bundle)
		if err != nil {
			return err
		}
		out, err := os.OpenFile(os.Getenv("GITHUB_OUTPUT"), os.O_APPEND|os.O_WRONLY, 0600)
		if err != nil {
			return err
		}
		defer out.Close()
		_, err = fmt.Fprintf(out, "request-id=%s\npublic-key=%s\nbundle=%s\nproduction-bundle=%s\n", hex.EncodeToString(id), base64.StdEncoding.EncodeToString(der), data, bad)
		return err
	}
	if os.Args[1] != "verify" {
		return fmt.Errorf("unknown probe command")
	}
	defer os.Remove(privatePath)
	der, err := os.ReadFile(privatePath)
	if err != nil {
		return err
	}
	private, err := x509.ParsePKCS1PrivateKey(der)
	if err != nil {
		return err
	}
	data, err := os.ReadFile(filepath.Join(os.Getenv("RUNNER_TEMP"), "ghenv-downloaded", "payload.json"))
	if err != nil {
		return err
	}
	var envelope struct {
		Version                string
		Key, Nonce, Ciphertext []byte
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		return err
	}
	if envelope.Version != "ghenv-v1" {
		return fmt.Errorf("unexpected protocol")
	}
	key, err := rsa.DecryptOAEP(sha256.New(), rand.Reader, private, envelope.Key, []byte("ghenv-v1"))
	if err != nil {
		return err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return err
	}
	if len(envelope.Nonce) != gcm.NonceSize() {
		return fmt.Errorf("invalid nonce")
	}
	plaintext, err := gcm.Open(nil, envelope.Nonce, envelope.Ciphertext, []byte(os.Getenv("TEST_REQUEST_ID")))
	if err != nil {
		return err
	}
	var got map[string]string
	if err := json.Unmarshal(plaintext, &got); err != nil {
		return err
	}
	if !reflect.DeepEqual(got, expected) {
		return fmt.Errorf("unexpected exported values or unrequested entries")
	}
	fmt.Println("Synthetic encrypted round trip passed; only requested entries were exported")
	return nil
}
