# Анализ аналогов и позиционирование

Обзор похожих утилит (GitHub, коммерческие продукты) и места `offline-docker-cli` на фоне них.  
Дата обзора: 2026-09-03.

## Суть продукта

`offline-docker-cli` — универсальная Python CLI для подготовки **portable offline-cache**, валидации, офлайн-сборки Docker-образов, `compose up` и **Trivy**-сканирования.

Ключевой workflow:

1. `discover` — зависимости из целевого репозитория  
2. `download-offline-cache` — единый кэш: debs, wheels, npm/yarn, docker images, Trivy DB  
3. `validate` → `load-docker-images` → `build-offline` → `up-offline` → `scan-trivy-offline`  
4. Конфиг в проекте (`.offline-docker.json` / `.yaml`); CLI без привязки к одному приложению  

Это не долгоживущее зеркало на LAN, а сценарий **«скачал бандл → перенёс → собрал/поднял офлайн»**.

## Вердикт

| Вопрос | Ответ |
|--------|--------|
| Первый в мире с идеей offline / air-gapped Docker? | **Нет** — тема давно известна в enterprise |
| Есть ли публичный 1:1 клон этой связки CLI? | **Скорее нет** |
| Уникальность | Project-scoped portable multi-ecosystem cache + offline build/up + Trivy в одном лёгком CLI |

Ниша реальная: у многих куски по отдельности; у нас — сквозной pipeline под corp / NeuroAI-стек.

---

## Категории аналогов

### 1. Долгоживущие зеркала / прокси (сервер на LAN)

Постоянный кэш в сети, а не «папка на флешке».

| Инструмент | Что кэширует | Ссылка |
|------------|--------------|--------|
| **Depsilo** | pip, apt, npm, Docker и ~10 экосистем; есть air-gap mode | https://depsilo.com/ |
| **LightMirrors** | DockerHub, k8s registries, PyPI, PyTorch, npm… | https://github.com/NoCLin/LightMirrors |
| **NORA** | Docker, npm, PyPI, APT, Maven, Cargo… (единый бинарь) | https://github.com/getnora-io/nora |
| Nexus / Artifactory / Harbor | Enterprise-стандарт private registry + proxy | коммерческие / self-hosted |

**Отличие от нас:** требуют развёрнутый сервис; наш CLI ориентирован на portable `offline-cache/` без обязательного зеркала (зеркала вроде ProGet/Nexus — опциональный слой resolve, см. план multi-source).

### 2. Record → перенос → offline replay

| Инструмент | Идея | Ссылка |
|------------|------|--------|
| **escrow-proxy** | MITM HTTP(S)-прокси: запись CI/CD-сессии в архив, offline replay | https://github.com/loopingz/escrow-proxy |

**Отличие:** прозрачный перехват трафика vs явный download по конфигу/discover и bind-mount кэша в Dockerfile.

### 3. Один слой экосистемы

| Слой | Примеры |
|------|---------|
| npm / pnpm | [pnpm-airgap](https://github.com/ReemX/pnpm-airgap), offline-npm-manager |
| Rust | [frostmirror](https://github.com/pillisan42/frostmirror) |
| Python wheels | ручные рецепты `pip download` / `--no-index --find-links` |
| Только образы | `docker save` / `load`, [Buncker](https://github.com/Rwx-G/Buncker), Red Hat **oc-mirror** |
| Trivy DB | официальный [air-gap / self-hosting](https://github.com/aquasecurity/trivy/blob/main/docs/guide/advanced/self-hosting.md) |

**Отличие:** закрывают один менеджер пакетов или только images; не собирают compose-стек end-to-end.

### 4. Ускорение онлайн-сборки (не air-gap)

BuildKit `RUN --mount=type=cache` для apt/pip/npm — ускоряет повторные билды при сети, **не** заменяет portable offline-cache для полностью отключённой машины.

### 5. Enterprise disconnected install

- **oc-mirror** (OpenShift / OKD) — зеркалирование образов и Helm в disconnected-кластер  
- Harbor + offline Trivy DB image  

Ближе к платформенной инфраструктуре кластера, чем к CLI для произвольного Docker Compose-проекта.

---

## Сравнительная матрица

| Возможность | offline-docker-cli | Depsilo / NORA / LightMirrors | escrow-proxy | pnpm-airgap / frostmirror | oc-mirror / Buncker |
|-------------|--------------------|-------------------------------|--------------|---------------------------|---------------------|
| Portable папка-кэш | ✅ | частично (export cache) | ✅ archive | ✅ | images / delta |
| APT + pip + npm + images | ✅ | ✅ (как registry) | косвенно | ❌ один слой | в основном images |
| Discover из проекта | ✅ | ❌ | ❌ | lockfile-only | Dockerfile / compose |
| Offline `docker build` + compose up | ✅ | нужна своя обвязка | нужна своя обвязка | ❌ | build / registry |
| Trivy offline DB + scan | ✅ | ❌ | ❌ | ❌ | ❌ (отдельно) |
| Без постоянно работающего сервера | ✅ | ❌ | proxy на время билда | ✅ | registry / USB kit |
| Project config (`.offline-docker.json`) | ✅ | свой config сервера | свой | CLI flags | ImageSet / CLI |

---

## Вывод для позиционирования

1. **Не претендуем** на «первый air-gap Docker tool» — рынок зрелый.  
2. **Претендуем** на узкую, но ценную нишу: лёгкий **project-scoped** CLI для multi-stack (Python + Node + APT + Docker + Trivy) с переносимым кэшем и командами build/up/scan.  
3. Ближайшие по духу — Depsilo / Artifactory / NORA, но они тяжелее и про **сервер-зеркало**; наш путь — **бандл + опциональные remote sources**.  
4. Имеет смысл в README/маркетинге явно противопоставлять: *«portable offline-cache workflow, not a LAN mirror»*.

## Источники обзора

- Depsilo, LightMirrors, NORA, escrow-proxy, frostmirror, pnpm-airgap, Buncker  
- Aqua Trivy self-hosting / air-gap docs  
- Red Hat oc-mirror (disconnected environments)  
- Stack Overflow / Docker forums: offline `docker build` + BuildKit metadata  
