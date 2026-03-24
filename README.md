<br />
<br />

<p align="center">
  <img width="600" src="sovran_systems_grey.png">
</p>

<br />
<br />
<br />

# Sovran_SystemsOS

**Own Your Stack. Run Your World.**

---

## 🌐 What is Sovran_SystemsOS?

Sovran_SystemsOS is a **declarative, self-hosted operating system built on NixOS** that turns a single machine into your:

* Personal cloud
* Private communications hub
* Bitcoin node
* Web server
* Daily desktop

This isn’t just an OS config — it’s a **complete sovereign computing environment**.

---

## ⚡ Why It Matters

Most people rely on a patchwork of third-party services:

* Cloud storage owned by corporations
* Messaging platforms that mine metadata
* Financial infrastructure you don’t control

Sovran_SystemsOS flips that model.

👉 You run the services.
👉 You own the data.
👉 You control the system.

---

## 🚀 What You’re Actually Getting

This system doesn’t just install apps — it **assembles an ecosystem**.

### 🖥 A Unified Desktop + Server

* Full GNOME desktop
* Ready for daily use *and* backend services
* Remote access capabilities

---

### 🌍 A Real Web Stack (Out of the Box)

* Caddy web server with automatic HTTPS
* Reverse proxy routing already wired
* Multi-service hosting under your domains

---

### ☁️ Your Own Cloud Platform

* Nextcloud → file storage, sync, collaboration
* WordPress → publish and host content
* Vaultwarden → secure password management

---

### 💬 Private Communication Layer

* Matrix Synapse → decentralized messaging backend
* Element support → modern chat + collaboration
* Optional voice/video infrastructure

---

### ₿ Sovereign Financial Stack

* Run your own Bitcoin node
* BTCPay Server for payments
* Optional mempool explorer

No intermediaries. No permissions.

---

### 🔐 Built-In Security Posture

* Hardened SSH (no password logins)
* Fail2ban active by default
* Tor integration available
* Encrypted secrets via Agenix

---

### 💾 Reliability Without Babysitting

* Automated backups (rsnapshot)
* Cron jobs for maintenance
* Database initialization included

---

## 🧠 What Makes It Stand Out

### 1. **This Is Not a “Toolkit” — It’s a System**

Most projects give you pieces.

Sovran_SystemsOS gives you a **pre-integrated stack** where:

* Services already talk to each other
* Reverse proxy is configured
* Databases are initialized
* Ports and firewall rules are handled

You’re not assembling — you’re **activating**.

---

### 2. **Feature Toggles = Power Without Bloat**

Turn features on or off like switches:

```nix id="z91x8a"
sovran_systemsOS.features.mempool = true;
sovran_systemsOS.features.haven = true;
```

No unnecessary services. No wasted resources.

---

### 3. **Reproducibility = Control**

Your entire system is code:

* Rebuild anytime
* Move to new hardware
* Roll back instantly

This is infrastructure you can trust because you can **recreate it exactly**.

---

### 4. **Automation Where It Counts**

A huge amount is handled for you:

* Service wiring
* Reverse proxy setup
* Scheduled jobs
* Base security

But unlike “black box” systems, you still retain **full visibility and control**.

---

## ⚠️ Honest Reality (No Hype)

This system **does not eliminate effort**.

You will still need to:

* Configure DNS and domains
* Manage secrets (Agenix)
* Understand your enabled services
* Perform initial setup steps

But here’s the difference:

👉 You’re not starting from scratch
👉 You’re not duct-taping services together
👉 You’re not fighting your system

You’re building on a **solid, opinionated foundation**

---

## 🔌 Expand As You Grow

Enable advanced features anytime:

```nix id="0p9k21"
sovran_systemsOS.features.bitcoin-core = true;
sovran_systemsOS.features.bip110 = true;
sovran_systemsOS.features.mempool = true;
sovran_systemsOS.features.rdp = true;
```

Available add-ons include:

* Bitcoin Core / Knots switching
* BIP-110 (enhanced Bitcoin consensus policy)
* Mempool explorer
* Nostr relay (Haven)
* Element voice/video backend
* Remote desktop

---

## 🛠 Installation

Full guide:

👉 https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/src/branch/main/DIY%20Install%20Sovran_SystemsOS.md

---

## 💬 Community

* General Chat:
  https://matrix.to/#/#sovran-systems:anarchyislove.xyz

* DIY Support:
  https://matrix.to/#/#DIY_Sovran_SystemsOS:anarchyislove.xyz

---

## 🧭 Who This Is For

Sovran_SystemsOS is for people who want to:

* Move off Big Tech platforms
* Run their own infrastructure
* Understand and control their system
* Build a sovereign digital life

---

## 🧭 Final Thought

You can keep renting your digital life…

Or you can start owning it.

Sovran_SystemsOS doesn’t promise magic.
It gives you something more valuable:

👉 **A system you control, understand, and can rebuild at will.**

---

**All Is Love. Fear Is Illusion. All Beings Are Free. Truth Can Never Be Destroyed.**

