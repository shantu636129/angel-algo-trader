# ============================================================
# ZENTEC ML TRADING SYSTEM - VERSION 10
# ============================================================
# 5-YEAR ROBUST WALK-FORWARD VALIDATION
#
# IMPORTANT:
# V10 will NOT force a strategy if the historical evidence
# is not robust enough.
#
# INPUT:
#   ZENTEC_daily_2y.csv
#
# CSV COLUMNS:
#   timestamp, open, high, low, close, volume
#
# OUTPUT:
#   ZENTEC_v10_predictions.csv
#   ZENTEC_v10_trades.csv
#   ZENTEC_v10_summary.csv
#   ZENTEC_v10_monthly.csv
#   ZENTEC_v10_yearly.csv
#   ZENTEC_v10_feature_importance.csv
#   ZENTEC_v10_candidate_scores.csv
#   ZENTEC_v10_robustness.csv
# ============================================================

import warnings
warnings.filterwarnings("ignore")

import os
import math
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score
)


# ============================================================
# CONFIGURATION
# ============================================================

CSV_FILE = "ZENTEC_daily_2y.csv"

MIN_TRAIN_ROWS = 180

FINAL_TEST_FRACTION = 0.20

ROUND_TRIP_COST = 0.001

# ------------------------------------------------------------
# V10 robustness rules
# ------------------------------------------------------------

MIN_VALIDATION_TRADES = 40
MIN_TRADES_PER_PERIOD = 8

MIN_PROFITABLE_PERIODS = 3

MIN_PERIOD_PF = 0.80

MIN_OVERALL_PF = 1.05

MIN_AVG_TRADE = 0.0

# ------------------------------------------------------------
# Probability thresholds
# ------------------------------------------------------------

THRESHOLDS = np.arange(
    0.35,
    0.801,
    0.05
)

# ------------------------------------------------------------
# Trading setups
# ------------------------------------------------------------

SETUPS = {

    "A_2pct_1pct_3d": {
        "target": 0.02,
        "stop": 0.01,
        "max_hold": 3
    },

    "B_3pct_1.5pct_3d": {
        "target": 0.03,
        "stop": 0.015,
        "max_hold": 3
    },

    "C_4pct_2pct_3d": {
        "target": 0.04,
        "stop": 0.02,
        "max_hold": 3
    },

    "D_5pct_2pct_5d": {
        "target": 0.05,
        "stop": 0.02,
        "max_hold": 5
    }
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_div(a, b):

    if isinstance(b, pd.Series):

        return a / b.replace(
            0,
            np.nan
        )

    if b == 0:

        return np.nan

    return a / b


def compound_returns(returns):

    if len(returns) == 0:

        return 0.0

    arr = np.array(
        returns,
        dtype=float
    )

    return float(
        np.prod(1.0 + arr) - 1.0
    )


def max_drawdown(returns):

    if len(returns) == 0:

        return 0.0

    arr = np.array(
        returns,
        dtype=float
    )

    equity = np.cumprod(
        1.0 + arr
    )

    peak = np.maximum.accumulate(
        equity
    )

    drawdown = (
        equity / peak
    ) - 1.0

    return float(
        drawdown.min()
    )


def profit_factor(returns):

    if len(returns) == 0:

        return 0.0

    arr = np.array(
        returns,
        dtype=float
    )

    gross_profit = arr[arr > 0].sum()

    gross_loss = abs(
        arr[arr < 0].sum()
    )

    if gross_loss == 0:

        if gross_profit > 0:

            return 999.0

        return 0.0

    return float(
        gross_profit / gross_loss
    )


def max_consecutive_losses(returns):

    maximum = 0
    current = 0

    for value in returns:

        if value < 0:

            current += 1

            maximum = max(
                maximum,
                current
            )

        else:

            current = 0

    return maximum


def sharpe_like(returns):

    if len(returns) < 2:

        return 0.0

    arr = np.array(
        returns,
        dtype=float
    )

    std = arr.std(
        ddof=1
    )

    if std == 0:

        return 0.0

    return float(
        arr.mean()
        / std
        * np.sqrt(len(arr))
    )


# ============================================================
# LOAD DATA
# ============================================================

print()
print("=" * 72)
print("ZENTEC ML TRADING SYSTEM - VERSION 10")
print("5-YEAR ROBUST WALK-FORWARD VALIDATION")
print("=" * 72)

if not os.path.exists(CSV_FILE):

    raise FileNotFoundError(
        "\nCSV file not found: "
        + CSV_FILE
        + "\n"
        "Make sure the CSV is in the same directory."
    )


df = pd.read_csv(
    CSV_FILE
)

print()
print(
    f"Input file: {CSV_FILE}"
)

print(
    f"Raw rows: {len(df)}"
)


# ============================================================
# STANDARDIZE COLUMN NAMES
# ============================================================

df.columns = [
    str(c).strip().lower()
    for c in df.columns
]


# ============================================================
# DATE COLUMN
# ============================================================

if "timestamp" in df.columns:

    df["date"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce"
    )

elif "date" in df.columns:

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

else:

    raise ValueError(
        "CSV must contain timestamp or date."
    )


required_columns = [
    "open",
    "high",
    "low",
    "close",
    "volume"
]


missing_columns = [
    c for c in required_columns
    if c not in df.columns
]


if missing_columns:

    raise ValueError(
        "Missing columns: "
        + str(missing_columns)
    )


df = df[
    [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]
].copy()


# ============================================================
# CLEAN DATA
# ============================================================

df = df.sort_values(
    "date"
)

df = df.drop_duplicates(
    subset=["date"],
    keep="last"
)

for column in required_columns:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


df = df.dropna(
    subset=required_columns + ["date"]
).reset_index(
    drop=True
)


print(
    f"Clean rows: {len(df)}"
)

print(
    f"Date range: "
    f"{df['date'].iloc[0]} -> "
    f"{df['date'].iloc[-1]}"
)


data_days = (
    df["date"].iloc[-1]
    - df["date"].iloc[0]
).days

years = (
    data_days / 365.25
)


print(
    f"Data span: {years:.2f} years"
)

if years >= 4.5:

    print(
        "5-year scale detected."
    )


# ============================================================
# DATA QUALITY
# ============================================================

print()
print("DATA QUALITY")
print("-" * 72)

print(
    f"Rows: {len(df)}"
)

print(
    f"Duplicate dates: "
    f"{df['date'].duplicated().sum()}"
)

print(
    "Missing values: "
    f"{df[required_columns].isna().sum().sum()}"
)


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def create_features(data):

    d = data.copy()

    # --------------------------------------------------------
    # Returns
    # --------------------------------------------------------

    d["return_1d"] = (
        d["close"].pct_change(1)
    )

    d["return_3d"] = (
        d["close"].pct_change(3)
    )

    d["return_5d"] = (
        d["close"].pct_change(5)
    )

    d["return_10d"] = (
        d["close"].pct_change(10)
    )

    d["return_20d"] = (
        d["close"].pct_change(20)
    )

    # --------------------------------------------------------
    # Candle structure
    # --------------------------------------------------------

    d["range_pct"] = safe_div(
        d["high"] - d["low"],
        d["close"]
    )

    d["body_pct"] = safe_div(
        abs(d["close"] - d["open"]),
        d["close"]
    )

    d["upper_wick_pct"] = safe_div(
        d["high"]
        - d[["open", "close"]].max(axis=1),
        d["close"]
    )

    d["lower_wick_pct"] = safe_div(
        d[["open", "close"]].min(axis=1)
        - d["low"],
        d["close"]
    )

    d["close_position"] = safe_div(
        d["close"] - d["low"],
        d["high"] - d["low"]
    )

    # --------------------------------------------------------
    # Moving averages
    # --------------------------------------------------------

    for period in [
        20,
        50,
        100,
        200
    ]:

        d[f"sma{period}"] = (
            d["close"]
            .rolling(period)
            .mean()
        )

        d[f"price_vs_sma{period}"] = (
            d["close"]
            / d[f"sma{period}"]
            - 1
        )

    # --------------------------------------------------------
    # Trend flags
    # --------------------------------------------------------

    d["above_sma20"] = (
        d["close"] > d["sma20"]
    ).astype(int)

    d["above_sma50"] = (
        d["close"] > d["sma50"]
    ).astype(int)

    d["above_sma100"] = (
        d["close"] > d["sma100"]
    ).astype(int)

    d["above_sma200"] = (
        d["close"] > d["sma200"]
    ).astype(int)

    d["sma20_above_sma50"] = (
        d["sma20"] > d["sma50"]
    ).astype(int)

    d["sma50_above_sma200"] = (
        d["sma50"] > d["sma200"]
    ).astype(int)

    # --------------------------------------------------------
    # Previous-day volume baselines
    #
    # IMPORTANT:
    # The current day's volume is NOT included in its
    # own baseline.
    # --------------------------------------------------------

    previous_volume = (
        d["volume"].shift(1)
    )

    for period in [
        5,
        10,
        20,
        50
    ]:

        d[f"volume_ma{period}"] = (
            previous_volume
            .rolling(period)
            .mean()
        )

        d[f"volume_ratio_{period}"] = safe_div(
            d["volume"],
            d[f"volume_ma{period}"]
        )

    # --------------------------------------------------------
    # Volume changes
    # --------------------------------------------------------

    d["volume_change_1d"] = (
        d["volume"].pct_change(1)
    )

    d["volume_change_3d"] = (
        d["volume"].pct_change(3)
    )

    d["volume_change_5d"] = (
        d["volume"].pct_change(5)
    )

    # --------------------------------------------------------
    # Current volume spike
    # --------------------------------------------------------

    d["current_spike"] = (
        d["volume_ratio_20"] > 1.5
    ).astype(int)

    # --------------------------------------------------------
    # Days since previous volume spike
    # --------------------------------------------------------

    days_since_spike = []

    last_spike = None

    for index, value in enumerate(
        d["current_spike"].fillna(0)
    ):

        if value == 1:

            if last_spike is None:

                days_since_spike.append(
                    0
                )

            else:

                days_since_spike.append(
                    index - last_spike
                )

            last_spike = index

        else:

            if last_spike is None:

                days_since_spike.append(
                    999
                )

            else:

                days_since_spike.append(
                    index - last_spike
                )

    d["days_since_spike"] = (
        days_since_spike
    )

    # --------------------------------------------------------
    # Previous highs
    #
    # Shift by 1 day to prevent leakage.
    # --------------------------------------------------------

    for period in [
        20,
        50,
        100,
        252
    ]:

        previous_high = (
            d["high"]
            .shift(1)
            .rolling(period)
            .max()
        )

        d[f"previous_high_{period}"] = (
            previous_high
        )

        d[f"distance_from_high{period}"] = (
            d["close"]
            / previous_high
            - 1
        )

    # --------------------------------------------------------
    # Momentum flags
    # --------------------------------------------------------

    d["positive_return_5d"] = (
        d["return_5d"] > 0
    ).astype(int)

    d["positive_return_10d"] = (
        d["return_10d"] > 0
    ).astype(int)

    d["strong_3d"] = (
        d["return_3d"] > 0.03
    ).astype(int)

    d["strong_5d"] = (
        d["return_5d"] > 0.05
    ).astype(int)

    # --------------------------------------------------------
    # Remove temporary columns
    # --------------------------------------------------------

    temporary = [
        "sma20",
        "sma50",
        "sma100",
        "sma200",
        "volume_ma5",
        "volume_ma10",
        "volume_ma20",
        "volume_ma50",
        "previous_high_20",
        "previous_high_50",
        "previous_high_100",
        "previous_high_252"
    ]

    d = d.drop(
        columns=[
            c for c in temporary
            if c in d.columns
        ]
    )

    return d


df = create_features(
    df
)


# ============================================================
# TARGET CREATION
# ============================================================
#
# Target = 1 when, during the NEXT 3 COMPLETE trading days:
#
#   1. At least one future day has volume spike
#   2. Future high reaches +3% from today's close
#
# IMPORTANT:
# Incomplete future windows remain NaN.
# They are NOT converted to target 0.
# ============================================================

future_spike = []
future_max_high = []

total_rows = len(df)

for i in range(total_rows):

    future = df.iloc[
        i + 1:
        min(i + 4, total_rows)
    ]

    if len(future) < 3:

        future_spike.append(
            np.nan
        )

        future_max_high.append(
            np.nan
        )

    else:

        spike_found = (
            future["volume_ratio_20"] > 1.5
        ).any()

        max_high = (
            future["high"].max()
        )

        future_spike.append(
            int(spike_found)
        )

        future_max_high.append(
            max_high
        )


df["future_spike"] = (
    future_spike
)

df["future_max_high"] = (
    future_max_high
)


df["target"] = np.nan


complete_target = (
    df["future_spike"].notna()
    &
    df["future_max_high"].notna()
)


df.loc[
    complete_target,
    "target"
] = (
    (
        df.loc[
            complete_target,
            "future_spike"
        ] == 1
    )
    &
    (
        df.loc[
            complete_target,
            "future_max_high"
        ]
        >=
        df.loc[
            complete_target,
            "close"
        ] * 1.03
    )
).astype(int)


# ============================================================
# FEATURE LIST
# ============================================================

excluded_columns = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "future_spike",
    "future_max_high",
    "target"
]


FEATURES = [
    c for c in df.columns
    if c not in excluded_columns
]


# ============================================================
# ML DATA
# ============================================================

ml_df = df[
    ["date"] + FEATURES + ["target"]
].copy()


ml_df = ml_df.dropna(
    subset=FEATURES + ["target"]
).reset_index(
    drop=True
)


ml_df["target"] = (
    ml_df["target"]
    .astype(int)
)


print()
print("ML DATA")
print("-" * 72)

print(
    f"Usable ML rows: {len(ml_df)}"
)

target_zero = (
    ml_df["target"] == 0
).sum()

target_one = (
    ml_df["target"] == 1
).sum()

print(
    f"Target 0: {target_zero}"
)

print(
    f"Target 1: {target_one}"
)

if len(ml_df) > 0:

    print(
        f"Positive rate: "
        f"{ml_df['target'].mean() * 100:.2f}%"
    )


# ============================================================
# WALK-FORWARD MODELING
# ============================================================

prediction_records = []

logistic_importances = []
rf_importances = []


print()
print("=" * 72)
print("WALK-FORWARD MODELING")
print("=" * 72)


for i in range(
    MIN_TRAIN_ROWS,
    len(ml_df)
):

    train = ml_df.iloc[
        :i
    ]

    test = ml_df.iloc[
        [i]
    ]

    X_train = train[
        FEATURES
    ]

    y_train = train[
        "target"
    ]

    X_test = test[
        FEATURES
    ]

    if y_train.nunique() < 2:

        continue

    # --------------------------------------------------------
    # Logistic Regression
    # --------------------------------------------------------

    logistic = Pipeline([
        (
            "scaler",
            StandardScaler()
        ),

        (
            "model",
            LogisticRegression(
                C=0.5,
                class_weight="balanced",
                max_iter=3000,
                random_state=42
            )
        )
    ])


    logistic.fit(
        X_train,
        y_train
    )


    logistic_probability = float(
        logistic.predict_proba(
            X_test
        )[0, 1]
    )


    # --------------------------------------------------------
    # Random Forest
    # --------------------------------------------------------

    rf = RandomForestClassifier(
        n_estimators=500,
        max_depth=6,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )


    rf.fit(
        X_train,
        y_train
    )


    rf_probability = float(
        rf.predict_proba(
            X_test
        )[0, 1]
    )


    # --------------------------------------------------------
    # Save prediction
    # --------------------------------------------------------

    prediction_records.append({

        "date":
            test["date"].iloc[0],

        "logistic_prob":
            logistic_probability,

        "rf_prob":
            rf_probability,

        "actual_target":
            int(
                test["target"].iloc[0]
            )
    })


    # --------------------------------------------------------
    # Feature importance
    # --------------------------------------------------------

    logistic_importances.append(
        np.abs(
            logistic
            .named_steps["model"]
            .coef_[0]
        )
    )

    rf_importances.append(
        rf.feature_importances_
    )


# ============================================================
# PREDICTIONS DATAFRAME
# ============================================================

predictions = pd.DataFrame(
    prediction_records
)


predictions = predictions.sort_values(
    "date"
).reset_index(
    drop=True
)


print(
    f"Walk-forward predictions: "
    f"{len(predictions)}"
)


if len(predictions) > 0:

    print(
        f"Prediction period: "
        f"{predictions['date'].iloc[0]}"
        f" -> "
        f"{predictions['date'].iloc[-1]}"
    )


# ============================================================
# MODEL METRICS
# ============================================================

print()
print("MODEL METRICS")
print("-" * 72)


for model_name in [
    "logistic",
    "rf"
]:

    probability_column = (
        f"{model_name}_prob"
    )

    predicted = (
        predictions[
            probability_column
        ] >= 0.50
    ).astype(int)

    actual = (
        predictions[
            "actual_target"
        ]
    )

    precision = precision_score(
        actual,
        predicted,
        zero_division=0
    )

    recall = recall_score(
        actual,
        predicted,
        zero_division=0
    )

    f1 = f1_score(
        actual,
        predicted,
        zero_division=0
    )

    print()
    print(
        model_name.upper()
    )

    print(
        f"Precision: {precision:.3f}"
    )

    print(
        f"Recall:    {recall:.3f}"
    )

    print(
        f"F1:        {f1:.3f}"
    )


# ============================================================
# TRADE SIMULATOR
# ============================================================

def simulate_trades(
    prediction_df,
    data,
    model_name,
    threshold,
    target_pct,
    stop_pct,
    max_hold
):

    if prediction_df is None:

        return pd.DataFrame()

    probability_column = (
        f"{model_name}_prob"
    )


    if probability_column not in prediction_df.columns:

        return pd.DataFrame()


    signals = prediction_df[
        prediction_df[
            probability_column
        ] >= threshold
    ].copy()


    if len(signals) == 0:

        return pd.DataFrame()


    data = data.reset_index(
        drop=True
    )


    date_to_index = {
        date: index
        for index, date
        in enumerate(
            data["date"]
        )
    }


    trades = []

    next_available_entry_index = 0


    for _, signal in signals.iterrows():

        signal_date = (
            signal["date"]
        )


        if signal_date not in date_to_index:

            continue


        signal_index = (
            date_to_index[
                signal_date
            ]
        )


        entry_index = (
            signal_index + 1
        )


        if entry_index >= len(data):

            continue


        # ----------------------------------------------------
        # No overlapping trades
        # ----------------------------------------------------

        if (
            entry_index
            <
            next_available_entry_index
        ):

            continue


        entry_row = (
            data.iloc[
                entry_index
            ]
        )


        entry_price = float(
            entry_row["open"]
        )


        if not np.isfinite(
            entry_price
        ):

            continue


        target_price = (
            entry_price
            * (1 + target_pct)
        )


        stop_price = (
            entry_price
            * (1 - stop_pct)
        )


        exit_index = None
        exit_price = None
        exit_reason = None


        last_index = min(
            entry_index
            + max_hold
            - 1,
            len(data) - 1
        )


        for j in range(
            entry_index,
            last_index + 1
        ):

            row = data.iloc[j]

            day_open = float(
                row["open"]
            )

            day_high = float(
                row["high"]
            )

            day_low = float(
                row["low"]
            )

            day_close = float(
                row["close"]
            )


            # ------------------------------------------------
            # Gap handling on entry day
            # ------------------------------------------------

            if j == entry_index:

                if (
                    day_open
                    >=
                    target_price
                ):

                    exit_index = j

                    exit_price = day_open

                    exit_reason = (
                        "TARGET_GAP"
                    )

                    break


                if (
                    day_open
                    <=
                    stop_price
                ):

                    exit_index = j

                    exit_price = day_open

                    exit_reason = (
                        "STOP_GAP"
                    )

                    break


            # ------------------------------------------------
            # Intraday stop / target
            #
            # If both are touched in same candle,
            # STOP is assumed first.
            # ------------------------------------------------

            hit_stop = (
                day_low
                <=
                stop_price
            )

            hit_target = (
                day_high
                >=
                target_price
            )


            if (
                hit_stop
                and
                hit_target
            ):

                exit_index = j

                exit_price = stop_price

                exit_reason = "STOP"

                break


            if hit_stop:

                exit_index = j

                exit_price = stop_price

                exit_reason = "STOP"

                break


            if hit_target:

                exit_index = j

                exit_price = target_price

                exit_reason = "TARGET"

                break


            # ------------------------------------------------
            # Time exit
            # ------------------------------------------------

            if j == last_index:

                exit_index = j

                exit_price = day_close

                exit_reason = "TIME_EXIT"

                break


        if exit_index is None:

            continue


        gross_return = (
            exit_price
            / entry_price
            - 1
        )


        net_return = (
            gross_return
            - ROUND_TRIP_COST
        )


        exit_date = (
            data.iloc[
                exit_index
            ]["date"]
        )


        hold_days = (
            exit_index
            - entry_index
            + 1
        )


        trades.append({

            "model":
                model_name,

            "signal_date":
                signal_date,

            "entry_date":
                entry_row["date"],

            "exit_date":
                exit_date,

            "entry_price":
                entry_price,

            "exit_price":
                exit_price,

            "target_price":
                target_price,

            "stop_price":
                stop_price,

            "probability":
                float(
                    signal[
                        probability_column
                    ]
                ),

            "threshold":
                threshold,

            "target_pct":
                target_pct,

            "stop_pct":
                stop_pct,

            "max_hold":
                max_hold,

            "hold_days":
                hold_days,

            "exit_reason":
                exit_reason,

            "gross_return":
                gross_return,

            "net_return":
                net_return
        })


        # ----------------------------------------------------
        # Next trade allowed only after this trade exits.
        # ----------------------------------------------------

        next_available_entry_index = (
            exit_index + 1
        )


    return pd.DataFrame(
        trades
    )


# ============================================================
# PERFORMANCE METRICS
# ============================================================

def calculate_metrics(
    trades
):

    if (
        trades is None
        or
        len(trades) == 0
    ):

        return {

            "trades": 0,

            "wins": 0,

            "losses": 0,

            "win_rate": 0.0,

            "avg_trade": 0.0,

            "median_trade": 0.0,

            "avg_win": 0.0,

            "avg_loss": 0.0,

            "profit_factor": 0.0,

            "compounded": 0.0,

            "max_drawdown": 0.0,

            "max_consecutive_losses": 0,

            "avg_hold": 0.0,

            "sharpe_like": 0.0
        }


    returns = (
        trades["net_return"]
        .astype(float)
        .tolist()
    )


    wins = [
        x for x in returns
        if x > 0
    ]


    losses = [
        x for x in returns
        if x < 0
    ]


    return {

        "trades":
            len(returns),

        "wins":
            len(wins),

        "losses":
            len(losses),

        "win_rate":
            len(wins)
            / len(returns),

        "avg_trade":
            float(
                np.mean(returns)
            ),

        "median_trade":
            float(
                np.median(returns)
            ),

        "avg_win":
            float(
                np.mean(wins)
            )
            if wins
            else 0.0,

        "avg_loss":
            float(
                np.mean(losses)
            )
            if losses
            else 0.0,

        "profit_factor":
            profit_factor(
                returns
            ),

        "compounded":
            compound_returns(
                returns
            ),

        "max_drawdown":
            max_drawdown(
                returns
            ),

        "max_consecutive_losses":
            max_consecutive_losses(
                returns
            ),

        "avg_hold":
            float(
                trades["hold_days"]
                .mean()
            ),

        "sharpe_like":
            sharpe_like(
                returns
            )
    }


# ============================================================
# CHRONOLOGICAL 80/20 SPLIT
# ============================================================

if len(predictions) < 100:

    raise ValueError(
        "Too few walk-forward predictions "
        "for reliable V10 validation."
    )


split_index = int(
    len(predictions)
    * (1 - FINAL_TEST_FRACTION)
)


validation_predictions = (
    predictions.iloc[
        :split_index
    ].copy()
)


final_predictions = (
    predictions.iloc[
        split_index:
    ].copy()
)


print()
print("=" * 72)
print("CHRONOLOGICAL 80/20 SPLIT")
print("=" * 72)

print(
    f"Validation predictions: "
    f"{len(validation_predictions)}"
)

print(
    f"Final test predictions: "
    f"{len(final_predictions)}"
)


print(
    f"Validation period: "
    f"{validation_predictions['date'].iloc[0]}"
    f" -> "
    f"{validation_predictions['date'].iloc[-1]}"
)


print(
    f"Final test period: "
    f"{final_predictions['date'].iloc[0]}"
    f" -> "
    f"{final_predictions['date'].iloc[-1]}"
)


# ============================================================
# FOUR VALIDATION PERIODS
# ============================================================

def split_four_periods(
    validation_df
):

    n = len(
        validation_df
    )

    boundaries = np.linspace(
        0,
        n,
        5,
        dtype=int
    )

    periods = []

    for i in range(4):

        periods.append(
            validation_df.iloc[
                boundaries[i]:
                boundaries[i + 1]
            ].copy()
        )

    return periods


validation_periods = (
    split_four_periods(
        validation_predictions
    )
)


print()
print("VALIDATION PERIODS")
print("-" * 72)


for i, period in enumerate(
    validation_periods,
    start=1
):

    if len(period) > 0:

        print(
            f"P{i}: "
            f"{period['date'].iloc[0]}"
            f" -> "
            f"{period['date'].iloc[-1]}"
            f" | rows={len(period)}"
        )


# ============================================================
# THRESHOLD STABILITY
# ============================================================

def threshold_stability(
    prediction_df,
    data,
    model_name,
    threshold,
    setup
):

    neighbour_pfs = []

    neighbours = [
        round(
            threshold - 0.05,
            2
        ),

        round(
            threshold + 0.05,
            2
        )
    ]


    for neighbour in neighbours:

        if (
            neighbour < 0.35
            or
            neighbour > 0.80
        ):

            continue


        neighbour_trades = simulate_trades(
            prediction_df,
            data,
            model_name,
            neighbour,
            setup["target"],
            setup["stop"],
            setup["max_hold"]
        )


        neighbour_metrics = (
            calculate_metrics(
                neighbour_trades
            )
        )


        if (
            neighbour_metrics["trades"]
            > 0
        ):

            neighbour_pfs.append(
                neighbour_metrics[
                    "profit_factor"
                ]
            )


    if len(neighbour_pfs) == 0:

        return 0.0


    return float(
        np.mean(
            neighbour_pfs
        )
    )


# ============================================================
# STRATEGY SEARCH
# ============================================================

candidate_rows = []

robust_rows = []


print()
print("=" * 72)
print("V10 STRATEGY SEARCH")
print("=" * 72)

print(
    f"Total models: 2"
)

print(
    f"Total setups: {len(SETUPS)}"
)

print(
    f"Total thresholds: {len(THRESHOLDS)}"
)

print(
    f"Total configurations: "
    f"{2 * len(SETUPS) * len(THRESHOLDS)}"
)


for model_name in [
    "logistic",
    "rf"
]:

    for setup_name, setup in SETUPS.items():

        for threshold_value in THRESHOLDS:

            threshold = float(
                round(
                    threshold_value,
                    2
                )
            )


            # ------------------------------------------------
            # Full validation
            # ------------------------------------------------

            validation_trades = (
                simulate_trades(
                    validation_predictions,
                    df,
                    model_name,
                    threshold,
                    setup["target"],
                    setup["stop"],
                    setup["max_hold"]
                )
            )


            overall = (
                calculate_metrics(
                    validation_trades
                )
            )


            # ------------------------------------------------
            # Minimum total trades
            # ------------------------------------------------

            if (
                overall["trades"]
                <
                MIN_VALIDATION_TRADES
            ):

                continue


            period_metrics = []

            profitable_periods = 0

            enough_period_trades = True


            for period_df in (
                validation_periods
            ):

                period_trades = (
                    simulate_trades(
                        period_df,
                        df,
                        model_name,
                        threshold,
                        setup["target"],
                        setup["stop"],
                        setup["max_hold"]
                    )
                )


                pm = (
                    calculate_metrics(
                        period_trades
                    )
                )


                period_metrics.append(
                    pm
                )


                if (
                    pm["trades"]
                    <
                    MIN_TRADES_PER_PERIOD
                ):

                    enough_period_trades = False


                if (
                    pm["profit_factor"]
                    > 1.0
                ):

                    profitable_periods += 1


            period_pfs = [
                x["profit_factor"]
                for x in period_metrics
            ]


            period_avgs = [
                x["avg_trade"]
                for x in period_metrics
            ]


            worst_period_pf = min(
                period_pfs
            )


            median_period_pf = float(
                np.median(
                    period_pfs
                )
            )


            neighbour_pf = (
                threshold_stability(
                    validation_predictions,
                    df,
                    model_name,
                    threshold,
                    setup
                )
            )


            # ------------------------------------------------
            # Strict robustness rule
            # ------------------------------------------------
            #
            # 1. >= 40 validation trades
            # 2. >= 8 trades in every period
            # 3. >= 3 of 4 periods PF > 1
            # 4. no period PF < 0.80
            # 5. overall PF >= 1.05
            # 6. positive average trade
            #
            # ------------------------------------------------

            robust = (

                overall["trades"]
                >= MIN_VALIDATION_TRADES

                and

                overall["profit_factor"]
                >= MIN_OVERALL_PF

                and

                overall["avg_trade"]
                > MIN_AVG_TRADE

                and

                profitable_periods
                >= MIN_PROFITABLE_PERIODS

                and

                worst_period_pf
                >= MIN_PERIOD_PF

                and

                enough_period_trades
            )


            # ------------------------------------------------
            # Stability score
            # ------------------------------------------------

            score = 0.0


            score += (
                math.log(
                    max(
                        overall[
                            "profit_factor"
                        ],
                        0.01
                    )
                )
                * 6
            )


            score += (
                overall[
                    "avg_trade"
                ]
                * 100
            )


            score += (
                math.log1p(
                    overall[
                        "trades"
                    ]
                )
                * 1.0
            )


            score += (
                worst_period_pf
                * 2.0
            )


            score += (
                median_period_pf
                * 1.5
            )


            score -= (
                abs(
                    overall[
                        "max_drawdown"
                    ]
                )
                * 8
            )


            score += (
                profitable_periods
                * 1.0
            )


            if neighbour_pf > 1.0:

                score += 1.5

            else:

                score -= 1.0


            if worst_period_pf < 0.80:

                score -= 5.0


            candidate = {

                "model":
                    model_name,

                "setup":
                    setup_name,

                "threshold":
                    threshold,

                "trades":
                    overall["trades"],

                "wins":
                    overall["wins"],

                "losses":
                    overall["losses"],

                "win_rate":
                    overall["win_rate"],

                "avg_trade":
                    overall["avg_trade"],

                "median_trade":
                    overall["median_trade"],

                "avg_win":
                    overall["avg_win"],

                "avg_loss":
                    overall["avg_loss"],

                "profit_factor":
                    overall["profit_factor"],

                "compounded":
                    overall["compounded"],

                "max_drawdown":
                    overall["max_drawdown"],

                "max_consecutive_losses":
                    overall[
                        "max_consecutive_losses"
                    ],

                "avg_hold":
                    overall["avg_hold"],

                "sharpe_like":
                    overall["sharpe_like"],

                "period1_trades":
                    period_metrics[0]["trades"],

                "period1_pf":
                    period_metrics[0]["profit_factor"],

                "period1_avg":
                    period_metrics[0]["avg_trade"],

                "period2_trades":
                    period_metrics[1]["trades"],

                "period2_pf":
                    period_metrics[1]["profit_factor"],

                "period2_avg":
                    period_metrics[1]["avg_trade"],

                "period3_trades":
                    period_metrics[2]["trades"],

                "period3_pf":
                    period_metrics[2]["profit_factor"],

                "period3_avg":
                    period_metrics[2]["avg_trade"],

                "period4_trades":
                    period_metrics[3]["trades"],

                "period4_pf":
                    period_metrics[3]["profit_factor"],

                "period4_avg":
                    period_metrics[3]["avg_trade"],

                "profitable_periods":
                    profitable_periods,

                "worst_period_pf":
                    worst_period_pf,

                "median_period_pf":
                    median_period_pf,

                "neighbor_threshold_pf":
                    neighbour_pf,

                "robust":
                    robust,

                "score":
                    score
            }


            candidate_rows.append(
                candidate
            )


            if robust:

                robust_rows.append(
                    candidate
                )


# ============================================================
# CANDIDATE DATAFRAME
# ============================================================

candidate_df = pd.DataFrame(
    candidate_rows
)

robust_df = pd.DataFrame(
    robust_rows
)


print()
print("=" * 72)
print("STRATEGY SEARCH RESULTS")
print("=" * 72)

print(
    f"Candidates with >= "
    f"{MIN_VALIDATION_TRADES} trades: "
    f"{len(candidate_df)}"
)

print(
    f"Robust configurations: "
    f"{len(robust_df)}"
)


if len(candidate_df) > 0:

    candidate_df = (
        candidate_df
        .sort_values(
            "score",
            ascending=False
        )
        .reset_index(
            drop=True
        )
    )


    print()
    print("TOP RESEARCH CANDIDATES")
    print("-" * 72)


    display_columns = [

        "model",
        "setup",
        "threshold",
        "trades",
        "win_rate",
        "avg_trade",
        "profit_factor",
        "compounded",
        "max_drawdown",
        "period1_pf",
        "period2_pf",
        "period3_pf",
        "period4_pf",
        "worst_period_pf",
        "profitable_periods",
        "neighbor_threshold_pf",
        "robust",
        "score"
    ]


    print(
        candidate_df[
            display_columns
        ].head(15).to_string(
            index=False,
            float_format=lambda x:
                f"{x:.4f}"
        )
    )


# ============================================================
# SELECT ROBUST STRATEGY
# ============================================================

selected_strategy = None


if len(robust_df) > 0:

    robust_df = (
        robust_df
        .sort_values(
            "score",
            ascending=False
        )
        .reset_index(
            drop=True
        )
    )


    selected_strategy = (
        robust_df.iloc[0].to_dict()
    )


    print()
    print("=" * 72)
    print("ROBUST STRATEGY FOUND")
    print("=" * 72)

    print(
        f"Model: "
        f"{selected_strategy['model']}"
    )

    print(
        f"Setup: "
        f"{selected_strategy['setup']}"
    )

    print(
        f"Threshold: "
        f"{selected_strategy['threshold']:.2f}"
    )

    print(
        f"Validation trades: "
        f"{selected_strategy['trades']}"
    )

    print(
        f"Validation PF: "
        f"{selected_strategy['profit_factor']:.2f}"
    )

    print(
        f"Validation compounded: "
        f"{selected_strategy['compounded'] * 100:.2f}%"
    )

    print(
        f"Validation max DD: "
        f"{selected_strategy['max_drawdown'] * 100:.2f}%"
    )

    print(
        f"Profitable periods: "
        f"{selected_strategy['profitable_periods']}/4"
    )

    print(
        f"Worst period PF: "
        f"{selected_strategy['worst_period_pf']:.2f}"
    )


else:

    print()
    print("=" * 72)
    print("NO ROBUST STRATEGY FOUND")
    print("=" * 72)

    print()
    print(
        "V10 WILL NOT FORCE A STRATEGY."
    )

    print()
    print(
        "LIVE TRADING STATUS:"
    )

    print(
        "NO ROBUST STRATEGY - DO NOT TRADE"
    )


    if len(candidate_df) > 0:

        best_research = (
            candidate_df.iloc[0]
        )

        print()
        print(
            "Best research candidate "
            "for diagnostics only:"
        )

        print(
            f"Model: "
            f"{best_research['model']}"
        )

        print(
            f"Setup: "
            f"{best_research['setup']}"
        )

        print(
            f"Threshold: "
            f"{best_research['threshold']:.2f}"
        )

        print(
            f"Trades: "
            f"{best_research['trades']}"
        )

        print(
            f"PF: "
            f"{best_research['profit_factor']:.2f}"
        )

        print(
            f"Profitable periods: "
            f"{best_research['profitable_periods']}/4"
        )

        print(
            f"Worst period PF: "
            f"{best_research['worst_period_pf']:.2f}"
        )


# ============================================================
# FINAL TEST
# ============================================================
#
# If a robust strategy exists:
#     use it.
#
# If no robust strategy exists:
#     use the best research candidate ONLY for diagnostics.
#
# It will NOT be considered a live strategy.
# ============================================================

final_test_strategy = None


if selected_strategy is not None:

    final_test_strategy = (
        selected_strategy
    )

elif len(candidate_df) > 0:

    final_test_strategy = (
        candidate_df.iloc[0].to_dict()
    )


final_trades = pd.DataFrame()


if final_test_strategy is not None:

    model_name = (
        final_test_strategy["model"]
    )

    setup_name = (
        final_test_strategy["setup"]
    )

    threshold = float(
        final_test_strategy["threshold"]
    )

    setup = SETUPS[
        setup_name
    ]


    final_trades = simulate_trades(
        final_predictions,
        df,
        model_name,
        threshold,
        setup["target"],
        setup["stop"],
        setup["max_hold"]
    )


final_metrics = calculate_metrics(
    final_trades
)


# ============================================================
# FINAL TEST BUY & HOLD
# ============================================================

buy_hold_return = 0.0


if len(final_predictions) > 1:

    first_date = (
        final_predictions[
            "date"
        ].iloc[0]
    )

    last_date = (
        final_predictions[
            "date"
        ].iloc[-1]
    )


    first_match = df.index[
        df["date"] == first_date
    ]

    last_match = df.index[
        df["date"] == last_date
    ]


    if (
        len(first_match) > 0
        and
        len(last_match) > 0
    ):

        first_index = int(
            first_match[0]
        )

        last_index = int(
            last_match[0]
        )


        if last_index > first_index:

            buy_hold_return = (
                df.iloc[
                    last_index
                ]["close"]
                /
                df.iloc[
                    first_index
                ]["close"]
                - 1
            )


# ============================================================
# FINAL TEST REPORT
# ============================================================

print()
print("=" * 72)
print("FINAL TEST")
print("=" * 72)


if selected_strategy is None:

    print(
        "STATUS: RESEARCH ONLY"
    )

    print(
        "No robust strategy passed V10."
    )

else:

    print(
        "STATUS: ROBUST STRATEGY"
    )


if final_test_strategy is not None:

    print()
    print(
        f"Model: "
        f"{final_test_strategy['model']}"
    )

    print(
        f"Setup: "
        f"{final_test_strategy['setup']}"
    )

    print(
        f"Threshold: "
        f"{final_test_strategy['threshold']:.2f}"
    )


print()
print(
    f"Final trades: "
    f"{final_metrics['trades']}"
)

print(
    f"Wins: "
    f"{final_metrics['wins']}"
)

print(
    f"Losses: "
    f"{final_metrics['losses']}"
)

print(
    f"Win rate: "
    f"{final_metrics['win_rate'] * 100:.2f}%"
)

print(
    f"Average trade: "
    f"{final_metrics['avg_trade'] * 100:.2f}%"
)

print(
    f"Profit factor: "
    f"{final_metrics['profit_factor']:.2f}"
)

print(
    f"Compounded: "
    f"{final_metrics['compounded'] * 100:.2f}%"
)

print(
    f"Max drawdown: "
    f"{final_metrics['max_drawdown'] * 100:.2f}%"
)

print(
    f"Buy & hold: "
    f"{buy_hold_return * 100:.2f}%"
)


strategy_vs_buy_hold = (
    final_metrics["compounded"]
    - buy_hold_return
)


print(
    f"Strategy - B&H: "
    f"{strategy_vs_buy_hold * 100:.2f}%"
)


# ============================================================
# FINAL TEST TRADES
# ============================================================

if len(final_trades) > 0:

    print()
    print("FINAL TEST TRADES")
    print("-" * 72)

    trade_columns = [

        "signal_date",
        "entry_date",
        "exit_date",
        "entry_price",
        "exit_price",
        "probability",
        "exit_reason",
        "net_return"
    ]


    print(
        final_trades[
            trade_columns
        ].to_string(
            index=False,
            float_format=lambda x:
                f"{x:.4f}"
        )
    )

else:

    print()
    print(
        "No final-test trades."
    )


# ============================================================
# LATEST SIGNAL
# ============================================================

print()
print("=" * 72)
print("LATEST SIGNAL")
print("=" * 72)


# ------------------------------------------------------------
# Latest row with complete features
# ------------------------------------------------------------

feature_ready = df.dropna(
    subset=FEATURES
).copy()


latest = (
    feature_ready.iloc[-1]
)


latest_date = (
    latest["date"]
)


latest_close = float(
    latest["close"]
)


# ============================================================
# TRAIN FINAL LOGISTIC MODEL
# ============================================================

X_all = ml_df[
    FEATURES
]

y_all = ml_df[
    "target"
]

X_latest = (
    latest[FEATURES]
    .to_frame()
    .T
)


final_logistic = Pipeline([
    (
        "scaler",
        StandardScaler()
    ),

    (
        "model",
        LogisticRegression(
            C=0.5,
            class_weight="balanced",
            max_iter=3000,
            random_state=42
        )
    )
])


final_logistic.fit(
    X_all,
    y_all
)


latest_logistic_probability = float(
    final_logistic.predict_proba(
        X_latest
    )[0, 1]
)


# ============================================================
# TRAIN FINAL RANDOM FOREST
# ============================================================

final_rf = RandomForestClassifier(
    n_estimators=500,
    max_depth=6,
    min_samples_leaf=5,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)


final_rf.fit(
    X_all,
    y_all
)


latest_rf_probability = float(
    final_rf.predict_proba(
        X_latest
    )[0, 1]
)


print(
    f"Latest date: "
    f"{latest_date}"
)

print(
    f"Latest close: "
    f"₹{latest_close:.2f}"
)

print()
print(
    f"Logistic probability: "
    f"{latest_logistic_probability * 100:.2f}%"
)

print(
    f"RF probability: "
    f"{latest_rf_probability * 100:.2f}%"
)


# ============================================================
# FINAL LIVE DECISION
# ============================================================

if selected_strategy is None:

    print()
    print(
        "FINAL DECISION: NO TRADE"
    )

    print(
        "Reason: "
        "No robust V10 strategy was found."
    )

else:

    locked_model = (
        selected_strategy["model"]
    )

    locked_threshold = float(
        selected_strategy["threshold"]
    )


    if locked_model == "logistic":

        selected_probability = (
            latest_logistic_probability
        )

    else:

        selected_probability = (
            latest_rf_probability
        )


    print()
    print(
        f"Locked model: "
        f"{locked_model}"
    )

    print(
        f"Locked threshold: "
        f"{locked_threshold:.2f}"
    )

    print(
        f"Selected probability: "
        f"{selected_probability * 100:.2f}%"
    )


    if (
        selected_probability
        >=
        locked_threshold
    ):

        print()
        print(
            "FINAL DECISION: TRADE SIGNAL"
        )

    else:

        print()
        print(
            "FINAL DECISION: NO TRADE"
        )


# ============================================================
# FEATURE IMPORTANCE
# ============================================================

feature_importance_rows = []


if len(logistic_importances) > 0:

    avg_logistic_importance = (
        np.mean(
            logistic_importances,
            axis=0
        )
    )


    for feature, importance in zip(
        FEATURES,
        avg_logistic_importance
    ):

        feature_importance_rows.append({

            "model":
                "logistic",

            "feature":
                feature,

            "importance":
                float(
                    importance
                )
        })


if len(rf_importances) > 0:

    avg_rf_importance = (
        np.mean(
            rf_importances,
            axis=0
        )
    )


    for feature, importance in zip(
        FEATURES,
        avg_rf_importance
    ):

        feature_importance_rows.append({

            "model":
                "rf",

            "feature":
                feature,

            "importance":
                float(
                    importance
                )
        })


feature_importance_df = (
    pd.DataFrame(
        feature_importance_rows
    )
)


if len(feature_importance_df) > 0:

    feature_importance_df = (
        feature_importance_df
        .sort_values(
            [
                "model",
                "importance"
            ],
            ascending=[
                True,
                False
            ]
        )
    )


# ============================================================
# MONTHLY RESULTS
# ============================================================

monthly_rows = []


if len(final_trades) > 0:

    monthly_trades = (
        final_trades.copy()
    )


    monthly_trades["month"] = (
        pd.to_datetime(
            monthly_trades[
                "exit_date"
            ]
        ).dt.to_period("M")
    )


    for month, group in (
        monthly_trades.groupby(
            "month"
        )
    ):

        metrics = (
            calculate_metrics(
                group
            )
        )


        monthly_rows.append({

            "month":
                str(month),

            "trades":
                metrics["trades"],

            "wins":
                metrics["wins"],

            "losses":
                metrics["losses"],

            "win_rate":
                metrics["win_rate"],

            "avg_trade":
                metrics["avg_trade"],

            "profit_factor":
                metrics["profit_factor"],

            "compounded":
                metrics["compounded"],

            "max_drawdown":
                metrics["max_drawdown"]
        })


monthly_df = pd.DataFrame(
    monthly_rows
)


# ============================================================
# YEARLY RESULTS
# ============================================================

yearly_rows = []


if len(final_trades) > 0:

    yearly_trades = (
        final_trades.copy()
    )


    yearly_trades["year"] = (
        pd.to_datetime(
            yearly_trades[
                "exit_date"
            ]
        ).dt.year
    )


    for year, group in (
        yearly_trades.groupby(
            "year"
        )
    ):

        metrics = (
            calculate_metrics(
                group
            )
        )


        yearly_rows.append({

            "year":
                int(year),

            "trades":
                metrics["trades"],

            "wins":
                metrics["wins"],

            "losses":
                metrics["losses"],

            "win_rate":
                metrics["win_rate"],

            "avg_trade":
                metrics["avg_trade"],

            "profit_factor":
                metrics["profit_factor"],

            "compounded":
                metrics["compounded"],

            "max_drawdown":
                metrics["max_drawdown"]
        })


yearly_df = pd.DataFrame(
    yearly_rows
)


# ============================================================
# SUMMARY
# ============================================================

if selected_strategy is not None:

    selected_model = (
        selected_strategy["model"]
    )

    selected_setup = (
        selected_strategy["setup"]
    )

    selected_threshold = (
        selected_strategy["threshold"]
    )

    validation_trades_count = (
        selected_strategy["trades"]
    )

    validation_pf = (
        selected_strategy["profit_factor"]
    )

    validation_compounded = (
        selected_strategy["compounded"]
    )

    validation_max_dd = (
        selected_strategy["max_drawdown"]
    )

else:

    selected_model = "NONE"

    selected_setup = "NONE"

    selected_threshold = np.nan

    validation_trades_count = 0

    validation_pf = 0.0

    validation_compounded = 0.0

    validation_max_dd = 0.0


summary_df = pd.DataFrame([{

    "version":
        "V10",

    "data_years":
        years,

    "raw_rows":
        len(df),

    "ml_rows":
        len(ml_df),

    "walkforward_predictions":
        len(predictions),

    "validation_predictions":
        len(validation_predictions),

    "final_predictions":
        len(final_predictions),

    "robust_configurations":
        len(robust_df),

    "selected_model":
        selected_model,

    "selected_setup":
        selected_setup,

    "selected_threshold":
        selected_threshold,

    "validation_trades":
        validation_trades_count,

    "validation_pf":
        validation_pf,

    "validation_compounded":
        validation_compounded,

    "validation_max_dd":
        validation_max_dd,

    "final_trades":
        final_metrics["trades"],

    "final_wins":
        final_metrics["wins"],

    "final_losses":
        final_metrics["losses"],

    "final_win_rate":
        final_metrics["win_rate"],

    "final_avg_trade":
        final_metrics["avg_trade"],

    "final_pf":
        final_metrics["profit_factor"],

    "final_compounded":
        final_metrics["compounded"],

    "final_max_dd":
        final_metrics["max_drawdown"],

    "buy_hold":
        buy_hold_return,

    "strategy_minus_buy_hold":
        strategy_vs_buy_hold,

    "latest_date":
        latest_date,

    "latest_close":
        latest_close,

    "latest_logistic_probability":
        latest_logistic_probability,

    "latest_rf_probability":
        latest_rf_probability,

    "live_status":
        (
            "ROBUST_STRATEGY"
            if selected_strategy is not None
            else
            "NO_ROBUST_STRATEGY_DO_NOT_TRADE"
        )
}])


# ============================================================
# SAVE ALL OUTPUTS
# ============================================================

predictions.to_csv(
    "ZENTEC_v10_predictions.csv",
    index=False
)


final_trades.to_csv(
    "ZENTEC_v10_trades.csv",
    index=False
)


summary_df.to_csv(
    "ZENTEC_v10_summary.csv",
    index=False
)


monthly_df.to_csv(
    "ZENTEC_v10_monthly.csv",
    index=False
)


yearly_df.to_csv(
    "ZENTEC_v10_yearly.csv",
    index=False
)


feature_importance_df.to_csv(
    "ZENTEC_v10_feature_importance.csv",
    index=False
)


candidate_df.to_csv(
    "ZENTEC_v10_candidate_scores.csv",
    index=False
)


robust_df.to_csv(
    "ZENTEC_v10_robustness.csv",
    index=False
)


# ============================================================
# FINAL OUTPUT
# ============================================================

print()
print("=" * 72)
print("V10 COMPLETE")
print("=" * 72)

print()
print("Files created:")

print(
    "  ZENTEC_v10_predictions.csv"
)

print(
    "  ZENTEC_v10_trades.csv"
)

print(
    "  ZENTEC_v10_summary.csv"
)

print(
    "  ZENTEC_v10_monthly.csv"
)

print(
    "  ZENTEC_v10_yearly.csv"
)

print(
    "  ZENTEC_v10_feature_importance.csv"
)

print(
    "  ZENTEC_v10_candidate_scores.csv"
)

print(
    "  ZENTEC_v10_robustness.csv"
)

print()

if selected_strategy is not None:

    print(
        "LIVE STATUS:"
    )

    print(
        "ROBUST STRATEGY FOUND"
    )

else:

    print(
        "LIVE STATUS:"
    )

    print(
        "NO ROBUST STRATEGY FOUND - DO NOT TRADE"
    )

print()
print("=" * 72)
