"""
Sample PySpark file for testing ctx map.
This simulates a real-world data pipeline to verify
that the skeleton generator works correctly.
"""

import os
import logging
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, when, lit, trim, lower
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

SPARK_CONFIG = {
    "spark.sql.adaptive.enabled": "true",
    "spark.sql.shuffle.partitions": "200",
    "spark.dynamicAllocation.enabled": "true",
}


class DataPipeline:
    """Main pipeline for processing user data from multiple sources."""

    def __init__(self, spark: SparkSession, config: Dict):
        self.spark = spark
        self.config = config
        self.source_path = config.get("source_path", "/data/raw")
        self.output_path = config.get("output_path", "/data/processed")
        self._validated = False
        logger.info(f"Pipeline initialized with config: {config}")

    def load_data(self, table_name: str, filters: Optional[Dict] = None) -> DataFrame:
        """Load data from a Hive table with optional filtering."""
        df = self.spark.table(table_name)
        if filters:
            for column, value in filters.items():
                df = df.filter(col(column) == value)
        logger.info(f"Loaded {df.count()} rows from {table_name}")
        return df

    def clean_data(self, df: DataFrame, drop_nulls: bool = True) -> DataFrame:
        """Clean dataframe by trimming strings and handling nulls."""
        string_cols = [f.name for f in df.schema.fields if f.dataType.simpleString() == "string"]
        for c in string_cols:
            df = df.withColumn(c, trim(lower(col(c))))
        if drop_nulls:
            df = df.dropna(subset=["user_id", "email"])
        df = df.dropDuplicates(["user_id"])
        return df

    def transform(self, df: DataFrame, rules: List[Dict]) -> DataFrame:
        """Apply transformation rules to the dataframe."""
        for rule in rules:
            col_name = rule["column"]
            operation = rule["operation"]
            if operation == "uppercase":
                df = df.withColumn(col_name, col(col_name))
            elif operation == "flag_null":
                df = df.withColumn(
                    f"{col_name}_is_null",
                    when(col(col_name).isNull(), lit(1)).otherwise(lit(0))
                )
        return df

    def validate(self, df: DataFrame) -> bool:
        """Run validation checks on the processed dataframe."""
        row_count = df.count()
        null_ids = df.filter(col("user_id").isNull()).count()
        duplicate_ids = row_count - df.select("user_id").distinct().count()
        is_valid = null_ids == 0 and duplicate_ids == 0 and row_count > 0
        self._validated = is_valid
        return is_valid

    def save(self, df: DataFrame, partition_cols: List[str] = None) -> str:
        """Save processed data to parquet format."""
        if not self._validated:
            raise RuntimeError("Data must be validated before saving")
        writer = df.write.mode("overwrite").format("parquet")
        if partition_cols:
            writer = writer.partitionBy(*partition_cols)
        writer.save(self.output_path)
        return self.output_path


def create_pipeline(env: str = "dev") -> DataPipeline:
    """Factory function to create a configured pipeline instance."""
    spark = SparkSession.builder.appName("data-pipeline").getOrCreate()
    for key, value in SPARK_CONFIG.items():
        spark.conf.set(key, value)
    config = {"source_path": f"/data/{env}/raw", "output_path": f"/data/{env}/processed"}
    return DataPipeline(spark, config)
