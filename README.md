# Cloudflare DDNS — Home Assistant Integration

[English](#english) | [中文](#中文)

---

## English

A Home Assistant custom integration that automatically updates Cloudflare DNS records (A and/or AAAA) to your current public IP address. Supports both IPv4 and IPv6, with HA entities to monitor the current IPs and trigger manual updates.

### Features

- Updates Cloudflare **A records** (IPv4) and/or **AAAA records** (IPv6)
- Automatically creates the DNS record if it doesn't exist
- Polls every **5 minutes** and only calls the Cloudflare API when the IP has changed
- Exposes HA entities:
  - `sensor` — current detected public IPv4 / IPv6
  - `sensor` — timestamp of the last successful DNS update
  - `button` — force an immediate update

### Requirements

- Home Assistant 2024.1+
- A Cloudflare account with your domain added as a zone
- A Cloudflare **API Token** with the `Zone:DNS:Edit` permission

> **How to create an API Token:**  
> Cloudflare Dashboard → My Profile → API Tokens → Create Token → Use the *Edit zone DNS* template → select your zone → Create Token.

### Installation

#### Manual

1. Copy the `custom_components/cloudflare_ddns/` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.

#### HACS

1. In HACS, go to **Integrations** → click the three-dot menu → **Custom repositories**.
2. Add `https://github.com/rudyll/cloudflare_for_ha` with category **Integration**.
3. Search for **Cloudflare DDNS** and install it.
4. Restart Home Assistant.

### Configuration

1. Go to **Settings → Integrations → Add Integration** and search for **Cloudflare DDNS**.
2. **Step 1 — Credentials & record:**
   | Field | Example |
   |---|---|
   | API Token | `your-cloudflare-api-token` |
   | Zone Name | `example.com` |
   | Record Name | `home.example.com` |
3. **Step 2 — Record types:** check **Update IPv4 (A)**, **Update IPv6 (AAAA)**, or both.
4. Click **Submit**. The integration validates your token and zone before saving.

### Entities

After setup the following entities are created (names use the record name as a prefix):

| Entity | Type | Description |
|---|---|---|
| `sensor.<slug>_ipv4` | Sensor | Current detected public IPv4 (only if IPv4 enabled) |
| `sensor.<slug>_ipv6` | Sensor | Current detected public IPv6 (only if IPv6 enabled) |
| `sensor.<slug>_last_updated` | Sensor (timestamp) | Time of the last successful DNS record change |
| `button.<slug>_force_update` | Button | Immediately trigger a DNS check and update |

### Customizing IP Detection URLs

After setup, click **Configure** on the integration card to override the default detection URLs.

| Field | Behavior |
|---|---|
| Custom IPv4 detection URLs | Comma-separated. Replaces the built-in IPv4 source list when non-empty. |
| Custom IPv6 fallback URLs | Comma-separated. Only used when the local interface cannot be read (see note below). |

> **IPv6 note:** IPv6 always reads the stable (non-temporary) address directly from the local network interface (`/proc/net/if_inet6`) first, bypassing external services entirely. This avoids the Privacy Extensions problem where outbound connections use a rotating temporary address. The IPv6 URLs are only a fallback for environments where `/proc/net/if_inet6` is unavailable (e.g. isolated Docker containers).

Leave either field blank to keep using the built-in defaults.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `cannot_connect` error during setup | Check HA can reach the internet; try again |
| `invalid_token` error | Verify the token has `Zone:DNS:Edit` permission |
| `zone_not_found` error | The zone name must match exactly what's in Cloudflare (e.g. `example.com`, not `www.example.com`) |
| IPv6 sensor stays `unavailable` | Your network may not have a public IPv6 address; disable IPv6 in the integration options |

---

## 中文

本项目是一个 Home Assistant 自定义集成，可自动将 Cloudflare 上的 DNS 记录（A 和/或 AAAA）更新为当前公网 IP 地址。支持 IPv4 和 IPv6 双栈，并通过 HA 实体展示当前 IP 状态、触发手动更新。

### 功能特性

- 支持更新 Cloudflare **A 记录**（IPv4）和/或 **AAAA 记录**（IPv6）
- 如果 DNS 记录不存在，自动创建
- 每 **5 分钟** 轮询一次，仅在 IP 变化时才调用 Cloudflare API
- 暴露以下 HA 实体：
  - `sensor` — 当前探测到的公网 IPv4 / IPv6
  - `sensor` — 上次成功更新 DNS 的时间戳
  - `button` — 立即触发一次更新

### 前置要求

- Home Assistant 2024.1 及以上版本
- Cloudflare 账号，且目标域名已添加为 Zone
- 一个具有 `Zone:DNS:Edit` 权限的 Cloudflare **API Token**

> **如何创建 API Token：**  
> Cloudflare 控制台 → 我的个人资料 → API 令牌 → 创建令牌 → 选择"编辑区域 DNS"模板 → 选择你的区域 → 创建令牌。

### 安装

#### 手动安装

1. 将 `custom_components/cloudflare_ddns/` 文件夹复制到 HA 的 `config/custom_components/` 目录下。
2. 重启 Home Assistant。

#### HACS 安装

1. 在 HACS 中点击右上角三点菜单 → **自定义存储库**。
2. 填入 `https://github.com/rudyll/cloudflare_for_ha`，类别选 **集成**。
3. 搜索 **Cloudflare DDNS** 并安装。
4. 重启 Home Assistant。

### 配置步骤

1. 进入 **设置 → 集成 → 添加集成**，搜索 **Cloudflare DDNS**。
2. **第一步 — 凭据与记录名：**
   | 字段 | 示例 |
   |---|---|
   | API Token | `你的 Cloudflare API Token` |
   | Zone 名称 | `example.com` |
   | 记录名称 | `home.example.com` |
3. **第二步 — 记录类型：** 勾选 **更新 IPv4（A）**、**更新 IPv6（AAAA）** 或两者都选。
4. 点击 **提交**。集成会在保存前验证 Token 和 Zone 是否有效。

### 实体说明

添加后将创建以下实体（名称以记录名为前缀）：

| 实体 | 类型 | 说明 |
|---|---|---|
| `sensor.<slug>_ipv4` | 传感器 | 当前探测到的公网 IPv4（仅启用 IPv4 时显示）|
| `sensor.<slug>_ipv6` | 传感器 | 当前探测到的公网 IPv6（仅启用 IPv6 时显示）|
| `sensor.<slug>_last_updated` | 传感器（时间戳）| 上次 DNS 记录实际变更的时间 |
| `button.<slug>_force_update` | 按钮 | 立即触发一次 DNS 检查与更新 |

### 自定义 IP 探测 URL

安装完成后，在集成卡片上点击**配置**，可以覆盖默认的 IP 探测地址。

| 字段 | 说明 |
|---|---|
| 自定义 IPv4 探测 URL | 逗号分隔，非空时替换内置的 IPv4 地址列表 |
| 自定义 IPv6 备用 URL | 逗号分隔，仅在本地接口读取失败时作为备用（见下方说明）|

> **IPv6 说明：** IPv6 探测优先直接读取本机网络接口（`/proc/net/if_inet6`）里的**稳定地址**，跳过 Privacy Extensions 产生的临时地址，不走任何外部 URL。IPv6 自定义 URL 仅在 `/proc/net/if_inet6` 不可用时（如隔离的 Docker 容器）才会生效。

两个字段留空则继续使用内置默认值。

### 常见问题

| 现象 | 解决方法 |
|---|---|
| 添加时报 `cannot_connect` | 检查 HA 网络是否正常，稍后重试 |
| 添加时报 `invalid_token` | 检查 Token 是否具有 `Zone:DNS:Edit` 权限 |
| 添加时报 `zone_not_found` | Zone 名称须与 Cloudflare 中完全一致（如 `example.com`，不是 `www.example.com`）|
| IPv6 传感器一直显示 `unavailable` | 当前网络可能没有公网 IPv6 地址，可在集成选项中关闭 IPv6 |

---

## License

MIT — see [LICENSE](LICENSE).
