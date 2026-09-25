# Angular Signals & Modern Best Practices Reference

Guidelines for writing idiomatic, fine-grained reactive Angular 17/18/19 applications.

---

## 1. Signal Architecture Pattern

```typescript
import { Component, ChangeDetectionStrategy, signal, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { OrderService } from '../services/order.service';

@Component({
  selector: 'app-order-summary',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="summary-card">
      <h3>Items: {{ totalCount() }}</h3>
      <p>Subtotal: {{ subtotal() | currency }}</p>
      <button (click)="applyDiscount()">Apply 10% Discount</button>
    </div>
  `
})
export class OrderSummaryComponent {
  private orderService = inject(OrderService);

  readonly items = signal<OrderItem[]>([]);
  readonly discountRate = signal<number>(0);

  // Computed values are lazily evaluated and memoized
  readonly totalCount = computed(() => this.items().reduce((sum, i) => sum + i.qty, 0));
  readonly subtotal = computed(() => {
    const raw = this.items().reduce((sum, i) => sum + (i.price * i.qty), 0);
    return raw * (1 - this.discountRate());
  });

  applyDiscount() {
    this.discountRate.set(0.10);
  }
}
```

---

## 2. Deferrable Views (`@defer`)

Prevent downloading heavy bundles until they enter the viewport:

```html
@defer (on viewport; prefetch on idle) {
  <app-analytics-chart [data]="analyticsData()" />
} @placeholder {
  <div class="skeleton-chart">Loading preview...</div>
} @loading (minimum 200ms) {
  <app-spinner />
} @error {
  <p class="error-state">Failed to load chart.</p>
}
```

---

## 3. RxJS to Signals Bridge

When dealing with Angular Router, HttpClient, or third-party observables:
```typescript
import { toSignal } from '@angular/core/rxjs-interop';

// Converts Observable directly into a signal, unsubscribing automatically on destroy
readonly user$ = this.authService.getCurrentUser();
readonly currentUser = toSignal(this.user$, { initialValue: null });
```
