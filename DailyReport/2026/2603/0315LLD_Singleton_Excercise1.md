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

## 回答(正解)

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
