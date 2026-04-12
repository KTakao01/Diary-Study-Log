#

## 自身の回答（間違い、6/10点）

```typescript
const LogLevel = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
} as const;
type LogLevel = (typeof LogLevel)[keyof typeof LogLevel];

class Logger {
  private minLevel: LogLevel = LogLevel.INFO;
  private logger?: Logger;

  setLevel(level: LogLevel): void {
    // TODO
    this.minLevel = level;
  }

  private log(level: LogLevel, message: string): void {
    // TODO: Only log if level >= minLevel
    if (level >= this.minLevel) {
      console.log(message);
    }
  }

  static getInstance(): Logger {
    if (!Logger.logger) {
      Logger.logger = new Logger();
    }
    return Logger.logger;
  }

  debug(msg: string): void {
    this.log(LogLevel.DEBUG, msg);
  }
  info(msg: string): void {
    this.log(LogLevel.INFO, msg);
  }
  warn(msg: string): void {
    this.log(LogLevel.WARN, msg);
  }
  error(msg: string): void {
    this.log(LogLevel.ERROR, msg);
  }
}

// TODO: Export as module-level singleton
// export { Logger }
// After implementing, usage should look like:
const l1 = Logger.getInstance();
const l2 = Logger.getInstance();
console.log("Same instance:", l1 === l2);
l1.setLevel(LogLevel.WARN);
l1.debug("Starting up");
l1.info("Server listening on port 8080");
l1.warn("Connection pool running low");
l1.error("Failed to connect to database");
```

【改善要求・バグの指摘（Actionable Feedback）】

出力フォーマットのバグ: ログ出力に [LEVEL] という接頭辞（プレフィックス）が欠けている（例：単なる メッセージ ではなく [WARN] メッセージ と出力しなければならない要件を満たしていない）。

privateコンストラクタの欠如: Singletonを強制するための private constructor が抜けている（※評価時のコードにおいて）。

変数名の統一: private static logger という変数名は、慣習に従って private static instance に変更すべき。

スレッドセーフの考慮: （前回のCounterと同様に）マルチスレッド環境を想定した排他制御の考慮が必要。」

## AIの回答：２回目(9/10点)

```typescript
const LogLevel = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
} as const;
type LogLevel = (typeof LogLevel)[keyof typeof LogLevel];

class Logger {
  private minLevel: LogLevel = LogLevel.INFO;
  private static instance?: Logger;
  private readonly levelNames = ["DEBUG", "INFO", "WARN", "ERROR"];

  private constructor() {}
  setLevel(level: LogLevel): void {
    this.minLevel = level;
  }
  private log(level: LogLevel, message: string): void {
    // スレッドセーフに関する考慮（コメントで明記）
    // Note: Node.jsのWorker Threads等を利用する際は、
    // ログ出力順序の競合を防ぐための排他制御を検討してください。
    if (level >= this.minLevel) {
      const levelName = this.levelNames[level];
      console.log(`[${levelName}] ${message}`);
    }
  }

  static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger();
    }
    return Logger.instance;
  }

  debug(msg: string): void {
    this.log(LogLevel.DEBUG, msg);
  }
  info(msg: string): void {
    this.log(LogLevel.INFO, msg);
  }
  warn(msg: string): void {
    this.log(LogLevel.WARN, msg);
  }
  error(msg: string): void {
    this.log(LogLevel.ERROR, msg);
  }
}

// After implementing, usage should look like:
const l1 = Logger.getInstance();
const l2 = Logger.getInstance();
console.log("Same instance:", l1 === l2);
l1.setLevel(LogLevel.WARN);
l1.debug("Starting up");
l1.info("Server listening on port 8080");
l1.warn("Connection pool running low");
l1.error("Failed to connect to database");
```
