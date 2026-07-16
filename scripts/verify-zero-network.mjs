// Empirical zero-network verification: monkey-patches every network entry
// point Node exposes (global fetch, http/https request, net.Socket.connect,
// dns.lookup/resolve, tls.connect) to throw before the real scan runs, then
// executes a real end-to-end scan against the committed fixtures. If the
// scan completes without any patched function firing, that is direct
// runtime proof -- not just a source grep -- that no code path in `scan`
// makes an outbound network call.
import net from 'node:net';
import tls from 'node:tls';
import dns from 'node:dns';
import http from 'node:http';
import https from 'node:https';

let calls = [];
function trap(label) {
  return () => {
    calls.push(label);
    throw new Error(`NETWORK CALL ATTEMPTED: ${label}`);
  };
}

globalThis.fetch = trap('global fetch()');
net.Socket.prototype.connect = trap('net.Socket.connect');
net.createConnection = trap('net.createConnection');
tls.connect = trap('tls.connect');
dns.lookup = trap('dns.lookup');
dns.resolve = trap('dns.resolve');
http.request = trap('http.request');
http.get = trap('http.get');
https.request = trap('https.request');
https.get = trap('https.get');

const { runScan } = await import(new URL('../dist/cli.js', import.meta.url).pathname);
const code = await runScan(new URL('../src/score/testdata/clips', import.meta.url).pathname, {
  json: true,
  out: new URL('../verify-zero-network-report.json', import.meta.url).pathname,
});

if (calls.length > 0) {
  console.error('FAILED: network calls were attempted:', calls);
  process.exit(1);
}
console.log(`OK: scan completed (exit code ${code}) with zero network calls attempted.`);
