# Singleton

Algomaster
https://algomaster.io/learn/lld/singleton-exercise
Exercise1

## 自身の回答（間違い）

```ts
// TODO: Implement as ES module singleton or class-based singleton

class Counter {
  private count: number = 0;
  private static counter: Counter;

  private constructor() {}

  increment(): void {
    // TODO: Increment count
    this.count++;
  }

  getCount(): number {
    // TODO: Return current count
    return this.count;
  }

  static getInstance(): Counter {
    if (!Counter.counter) {
      Counter.counter = new Counter();
      return Counter.counter;
    }
  }
}

export const counter = new Counter();

// After implementing, usage should look like:
const c1 = Counter.getInstance();
const c2 = Counter.getInstance();
console.log("Same instance:", c1 === c2);
for (let i = 0; i < 5; i++) {
  c1.increment();
}
console.log("Count after 5 increments:", c1.getCount());
```

インスタンスがあるときもないときも唯一のインスタンスを返す必要がある。

## 回答(不正解)

```ts
// TODO: Implement as ES module singleton or class-based singleton

class Counter {
  private count: number = 0;
  private static counter: Counter;

  private constructor() {}

  increment(): void {
    // TODO: Increment count
    this.count++;
  }

  getCount(): number {
    // TODO: Return current count
    return this.count;
  }

  static getInstance(): Counter {
    if (!Counter.counter) {
      Counter.counter = new Counter();
    }
    return Counter.counter;
  }
}

export const counter = new Counter();

// After implementing, usage should look like:
const c1 = Counter.getInstance();
const c2 = Counter.getInstance();
console.log("Same instance:", c1 === c2);
for (let i = 0; i < 5; i++) {
  c1.increment();
}
console.log("Count after 5 increments:", c1.getCount());
```

クラスの外側で export const counter = new Counter(); と書いてしまうと、門番（getInstance）を無視して、無理やり2つ目の新しい実体を作ろうとしてしまうことになる。だからSingleton（単一であること）が崩壊してしまう、

## 20260411.自身の回答（8/10点）

```typescript
class Counter {
  private count: number = 0;
  private static instance: Counter;
  //private instance: Counter;とした
  // static が無い private instance: Counter; だと、間違えて new Counter() を10回やったら、10個の実体の中に、それぞれ別々の instance という箱が10個誕生してしまいます。 これでは『全体で1つだけ』になりません。

  private constructor() {}
  //つまり、あなたが書かなくても、裏では public constructor() {} がこっそり動いていたため、エラーにならず正常に動作したのです。」
  // constructor忘れ
  //peScript（およびJavaScriptやJavaなど多くの言語）では、クラスにコンストラクタを一つも書かなかった場合、『空の public コンストラクタ（誰でも使える透明なコンストラクタ）』が自動的に裏で作成される仕様になっています。

  //コンストラクタの最大の役割は、『新しく実体（インスタンス）を作るときに、外からデータ（引数）を受け取って、その実体専用の初期設定をすること』
  //プロパティのところで直接 = 0 と書いた方がスッキリするので、今回はコンストラクタの中に書くことが何も無くなって『空（から）』になった。
  increment(): void {
    this.count++;
  }

  getCount(): number {
    return this.count;
  }

  static getInstance(): Counter {
    if (!this.instance) {
      this.instance = new Counter(); // new Counter;とした
    }
    return this.instance;
  }
  // staticをつけていなかった。
  // 今の君のコードのように static がついていないメソッド（getInstance）は、『 new Counter() で作られた後の実体』からしか呼べない。
  // つまり、getInstance() を呼んで実体を手に入れたいのに、そもそも getInstance() を呼ぶために実体（new Counter()）が必要になってしまう
}
export const counter = Counter.getInstance();

// this.getInstance()にした

// 動作確認
const c1 = counter;
const c2 = counter;
console.log("Same instance:", c1 === c2);
for (let i = 0; i < 5; i++) {
  c1.increment();
}
console.log("Count after 5 increments:", c1.getCount());
// console.log("Same instance:", c1 === c2); //　シングルトンなのでtrue
```

## 20260411.自身の回答（9/10点）

````typescript
class Counter {
  private count: number = 0;
  private static instance?: Counter; // ① null 明示で意図を明確化

  private constructor() {}

  increment(): void {
    this.count++;
  }

  getCount(): number {
    return this.count;
  }

  static getInstance(): Counter {
    if (!Counter.instance) {
      // ② this → Counter で外部参照を明示
      Counter.instance = new Counter();
    }
    return Counter.instance;
  }
}

// ④ 定数エクスポートをやめ、利用側が getInstance() を呼ぶパターンに統一
// export const counter = Counter.getInstance(); ← 削除

// --- 利用例: 異なるコンポーネントからの取得を明示 ---
const c1 = Counter.getInstance(); // Component A
const c2 = Counter.getInstance(); // Component B

console.log("Same instance:", c1 === c2); // true

for (let i = 0; i < 5; i++) {
  c1.increment();
}
console.log("Count after 5 increments:", c1.getCount()); // 5```
````

事前初期化（Eager Initialization）

仕組み: プログラムが起動してクラスが読み込まれた瞬間に、問答無用で先にインスタンスを作ってしまう方法。

コード例: private static readonly instance: Counter = new Counter();

遅延初期化（Lazy Initialization）

仕組み: 誰かが初めて getInstance() を呼んだ時に、「おっ、必要になったか」と初めてインスタンスを作る方法。

コード例: if (!Counter.instance) { Counter.instance = new Counter(); }」

普通、クラスの中で this と言えば、**『newされて生まれた自分自身（インスタンス）』**を指すのが圧倒的に多いよね。this.count++ のように。

でも、static メソッドの中だけは例外で、this はインスタンスではなく**『クラス自身（Counterという設計図）』**を指す仕様になっている。だから static getInstance() の中で this.instance と書いてもプログラム的には正しく動くんだ。」

マルチスレッド環境での競合を防ぐ書き方

```typescript
// メモリ上に「4バイト（32ビット）の共有スペース」を確保する
const sharedBuffer = new SharedArrayBuffer(4);

// その共有スペースを「32ビットの整数」として扱うための窓口を作る
const sharedCount = new Int32Array(sharedBuffer);

function atomicIncrement() {
  // sharedCountの 0番目の位置 に 1 を「不可分（アトミック）」に足す
  Atomics.add(sharedCount, 0, 1);
}
```

普通のメソッド（incrementなど）の this：
new されて出来上がった**『実体（オブジェクト）』のこと。クラス関連というより、クラス（設計図）から生み出された『作品そのもの』**だね。

static メソッド（getInstanceなど）の this：
作品を生み出す前の**『クラス自身（設計図そのもの）』**のこと。

### 参考(マルチスレッドセーフ)

```typescript
// ============================================================
// Thread-Safe Singleton (Worker Threads environments)
// SharedArrayBuffer is managed internally — callers don't need
// to handle shared memory directly.
// ============================================================
class ThreadSafeCounter {
  private static instance?: ThreadSafeCounter;

  // Internal shared buffer: created once and reused across all getInstance() calls
  private static readonly sharedBuffer = new SharedArrayBuffer(
    Int32Array.BYTES_PER_ELEMENT,
  );
  private readonly count: Int32Array;

  private constructor() {
    // Bind to the class-level shared buffer
    this.count = new Int32Array(ThreadSafeCounter.sharedBuffer);
  }

  increment(): void {
    Atomics.add(this.count, 0, 1); // Atomic add — no race condition
  }

  getCount(): number {
    return Atomics.load(this.count, 0); // Atomic read — always up-to-date
  }

  // Returns the shared buffer so Workers can bind to the same memory
  static getSharedBuffer(): SharedArrayBuffer {
    return ThreadSafeCounter.sharedBuffer;
  }

  static getInstance(): ThreadSafeCounter;
  static getInstance(buffer: SharedArrayBuffer): ThreadSafeCounter;
  static getInstance(buffer?: SharedArrayBuffer): ThreadSafeCounter {
    if (!ThreadSafeCounter.instance) {
      // Workers receive the buffer via workerData and rebind to it
      if (buffer) {
        const temp = new ThreadSafeCounter();
        temp.count.set(new Int32Array(buffer));
        Object.assign(temp, { count: new Int32Array(buffer) });
        ThreadSafeCounter.instance = temp;
      } else {
        ThreadSafeCounter.instance = new ThreadSafeCounter();
      }
    }
    return ThreadSafeCounter.instance;
  }
}

// ============================================================
// Usage
// ============================================================
if (isMainThread) {
  console.log("=== Simple Singleton (single-threaded) ===");
  const c1 = Counter.getInstance(); // Component A
  const c2 = Counter.getInstance(); // Component B
  console.log("Same instance:", c1 === c2); // true

  for (let i = 0; i < 5; i++) c1.increment();
  console.log("Count after 5 increments:", c2.getCount()); // 5

  console.log("\n=== Thread-Safe Singleton (Worker Threads) ===");
  const WORKERS = 2;
  const INCREMENTS_PER_WORKER = 1000;
  const sharedBuffer = ThreadSafeCounter.getSharedBuffer();
  let finished = 0;

  for (let i = 0; i < WORKERS; i++) {
    const worker = new Worker(__filename, {
      workerData: { buffer: sharedBuffer, increments: INCREMENTS_PER_WORKER },
    });

    worker.on("exit", () => {
      finished++;
      if (finished === WORKERS) {
        const counter = ThreadSafeCounter.getInstance();
        console.log(`Expected : ${WORKERS * INCREMENTS_PER_WORKER}`); // 2000
        console.log(`Actual   : ${counter.getCount()}`); // 2000
      }
    });
  }
} else {
  const { buffer, increments } = workerData as {
    buffer: SharedArrayBuffer;
    increments: number;
  };
  // Worker binds to the same shared buffer passed from the main thread
  const counter = ThreadSafeCounter.getInstance(buffer);
  for (let i = 0; i < increments; i++) counter.increment();
}
```
