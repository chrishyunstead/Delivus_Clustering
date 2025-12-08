import asyncio

import pandas as pd


class ShippingProcessor:
    def __init__(self, db_handler):
        """Class for processing shipping item data"""
        self.db_handler = db_handler

    def get_queries(
        self,
        pickup_batch_uuids,
        return_order_shop_uuids,
        start_time,
        end_time,
        shipping_shop_uuids,
        exclude_sector_ids,
        delivery_date,
        delivery_date_shop_uuids,
    ):
        """Generate SQL queries for fetching shipping data"""
        queries = []

        if start_time:
            end_time = end_time if end_time else "NOW()"
            queries.append(
                f"""
                    SELECT 
                        shipping_shippingitem.`uuid` as 'shipping_uuid',
                        shipping_shippingitem.tracking_number as 'tracking_number',
                        DATE_FORMAT(DATE_ADD(shipping_shippingitem.timestamp_pickup, INTERVAL 9 HOUR),'%Y-%m-%d') as 'pickup_date',
                        shipping_shippingitem.designated_sector_id as 'item_sector',
                        regexp_replace(location_sector.code, '[0-9]', '') as 'Area',
                        location_sector.code as 'code',
                        location_address.lat as 'lat',
                        location_address.lng as 'lng',
                        shipping_shippingitem.status as 'shipping_status',
                        0 as 'is_scanned',
                        location_address.zipcode as 'zipcode'
                    FROM shipping_shippingitem
                    JOIN location_address
                    ON shipping_shippingitem.address_id = location_address.id
                    JOIN location_sector
                    ON shipping_shippingitem.designated_sector_id = location_sector.id
                    JOIN order_order
                    ON shipping_shippingitem.order_id = order_order.id
                    JOIN shop_shop
                    ON order_order.shop_id = shop_shop.id
                    WHERE shipping_shippingitem.status = 'CREATED'
                    AND DATE_FORMAT(DATE_ADD(shipping_shippingitem.timestamp_created, INTERVAL 9 HOUR),'%Y-%m-%d %H:%i') BETWEEN '{start_time}' AND '{end_time}'
                    AND shop_shop.`uuid` IN ({shipping_shop_uuids})
                    AND location_sector.id NOT IN ({exclude_sector_ids})
                """
            )

        if pickup_batch_uuids:
            queries.append(
                f"""
                    SELECT 
                        shipping_shippingitem.`uuid` as 'shipping_uuid',
                        shipping_shippingitem.tracking_number as 'tracking_number',
                        DATE_FORMAT(DATE_ADD(shipping_shippingitem.timestamp_pickup, INTERVAL 9 HOUR),'%Y-%m-%d') as 'pickup_date',
                        shipping_shippingitem.designated_sector_id as 'item_sector',
                        regexp_replace(location_sector.code, '[0-9]', '') as 'Area',
                        location_sector.code as 'code',
                        location_address.lat as 'lat',
                        location_address.lng as 'lng',
                        shipping_shippingitem.status as 'shipping_status',
                        0 as 'is_scanned',
                        location_address.zipcode as 'zipcode'
                    FROM shipping_shippingitem
                    JOIN location_address
                    ON shipping_shippingitem.address_id = location_address.id
                    JOIN location_sector
                    ON shipping_shippingitem.designated_sector_id = location_sector.id
                    JOIN route_pickupbatch
                    ON shipping_shippingitem.pickup_batch_id = route_pickupbatch.id
                    WHERE shipping_shippingitem.is_return = False
                    AND shipping_shippingitem.status IN ("READYFORPICKUP", "PICKUPASSIGNED", "PICKUPCOMPLETED", "WAITINGFORSORT")
                    AND route_pickupbatch.uuid IN ({pickup_batch_uuids})
                    AND location_sector.id NOT IN ({exclude_sector_ids})
                """
            )

        if return_order_shop_uuids:
            queries.append(
                f"""
                    SELECT
                        shipping_shippingitem.`uuid` as 'shipping_uuid',
                        shipping_shippingitem.tracking_number as 'tracking_number',
                        DATE_FORMAT(DATE_ADD(shipping_shippingitem.timestamp_pickup, INTERVAL 9 HOUR),'%Y-%m-%d') as 'pickup_date',
                        shipping_shippingitem.designated_sector_id as 'item_sector',
                        regexp_replace(location_sector.code, '[0-9]', '') as 'Area',
                        location_sector.code as 'code',
                        location_address.lat as 'lat',
                        location_address.lng as 'lng',
                        shipping_shippingitem.status as 'shipping_status',
                        0 as 'is_scanned',
                        location_address.zipcode as 'zipcode'
                    FROM shipping_shippingitem
                    JOIN location_address
                    ON shipping_shippingitem.address_id = location_address.id
                    JOIN location_sector
                    ON shipping_shippingitem.designated_sector_id = location_sector.id
                    JOIN order_order
                    ON shipping_shippingitem.order_id = order_order.id
                    JOIN shop_shop
                    ON order_order.shop_id = shop_shop.id
                    WHERE shipping_shippingitem.is_return = True
                    AND shipping_shippingitem.status = 'RETURN_WAITINGFORSORT'
                    AND shop_shop.uuid IN ({return_order_shop_uuids})
                    AND location_sector.id NOT IN ({exclude_sector_ids})
                    UNION
                    SELECT
                        shipping_shippingitem.`uuid` as 'shipping_uuid',
                        shipping_shippingitem.tracking_number as 'tracking_number',
                        DATE_FORMAT(DATE_ADD(shipping_shippingitem.timestamp_pickup, INTERVAL 9 HOUR),'%Y-%m-%d') as 'pickup_date',
                        shipping_shippingitem.designated_sector_id as 'item_sector',
                        regexp_replace(location_sector.code, '[0-9]', '') as 'Area',
                        location_sector.code as 'code',
                        location_address.lat as 'lat',
                        location_address.lng as 'lng',
                        shipping_shippingitem.status as 'shipping_status',
                        0 as 'is_scanned',
                        location_address.zipcode as 'zipcode'
                    FROM shipping_shippingitem
                    JOIN location_address
                    ON shipping_shippingitem.address_id = location_address.id
                    JOIN location_sector
                    ON shipping_shippingitem.designated_sector_id = location_sector.id
                    JOIN order_order
                    ON shipping_shippingitem.order_id = order_order.id
                    JOIN shop_shop
                    ON order_order.shop_id = shop_shop.id
                    WHERE shipping_shippingitem.is_return = True
                    AND shop_shop.return_process_without_info = True
                    AND shipping_shippingitem.status = 'RETURN_CREATED'
                    AND shop_shop.uuid IN ({return_order_shop_uuids})
                    AND location_sector.id NOT IN ({exclude_sector_ids})
                """
            )

        if delivery_date_shop_uuids:
            queries.append(
                f"""
                    SELECT 
                        shipping_shippingitem.`uuid` as 'shipping_uuid',
                        shipping_shippingitem.tracking_number as 'tracking_number',
                        DATE_FORMAT(DATE_ADD(shipping_shippingitem.timestamp_pickup, INTERVAL 9 HOUR),'%Y-%m-%d') as 'pickup_date',
                        shipping_shippingitem.designated_sector_id as 'item_sector',
                        regexp_replace(location_sector.code, '[0-9]', '') as 'Area',
                        location_sector.code as 'code',
                        location_address.lat as 'lat',
                        location_address.lng as 'lng',
                        shipping_shippingitem.status as 'shipping_status',
                        0 as 'is_scanned',
                        location_address.zipcode as 'zipcode'
                    FROM shipping_shippingitem
                    JOIN location_address
                    ON shipping_shippingitem.address_id = location_address.id
                    JOIN location_sector
                    ON shipping_shippingitem.designated_sector_id = location_sector.id
                    JOIN order_order
                    ON shipping_shippingitem.order_id = order_order.id
                    JOIN shop_shop
                    ON order_order.shop_id = shop_shop.id
                    WHERE shipping_shippingitem.status IN ('CREATED', 'READYFORPICKUP')
                    AND shop_shop.`uuid` IN ({delivery_date_shop_uuids})
                    AND JSON_EXTRACT(order_order.metadata, '$.delivery_date') = '{delivery_date}'
                    AND location_sector.id NOT IN ({exclude_sector_ids})
                """
            )

        return queries

    async def fetch_data(self, query):
        return await self.db_handler.fetch_data_async(query)

    async def get_shipping_items_dataset(
        self,
        pickup_batch_uuids,
        return_order_shop_uuids,
        start_time,
        end_time,
        shipping_shop_uuids,
        exclude_sector_ids,
        delivery_date,
        delivery_date_shop_uuids,
    ):
        """Fetch shipping data using asynchronous parallel processing"""
        queries = self.get_queries(
            pickup_batch_uuids,
            return_order_shop_uuids,
            start_time,
            end_time,
            shipping_shop_uuids,
            exclude_sector_ids,
            delivery_date,
            delivery_date_shop_uuids,
        )

        tasks = [self.fetch_data(query) for query in queries]
        results = await asyncio.gather(*tasks)

        combined_results = [item for sublist in results for item in sublist]

        print(f"len_queries: {len(queries)}")
        print(f"queries: {queries}")
        print(f"len_combined_results: {len(combined_results)}")

        if not combined_results:
            print("No shipping items found.")
            return None

        df_raw_items = pd.DataFrame(combined_results)
        df_items = df_raw_items.drop_duplicates(subset=["shipping_uuid"])

        return df_items

    def get_cluster_data(self, plan_date, plan_no):
        """Fetch last cluster data for a specific date"""
        query = f"""
            SELECT 
                shipping_shippingitem.`uuid` as 'shipping_uuid',
                shipping_shippingitem.tracking_number as 'tracking_number',
                shipping_shippingitem.designated_sector_id as 'item_sector',
                regexp_replace(location_sector.code, '[0-9]', '') as 'Area',
                location_sector.code as 'code',
                location_address.lat as 'lat',
                location_address.lng as 'lng',
                shipping_shippingitem.status as 'shipping_status',
                location_address.zipcode as 'zipcode',
                hub_cluster_plan.bunny_color as 'driver_type',
                hub_cluster_plan.sector_code as 'driver_code',
                hub_cluster_plan.cluster_id as 'cluster_label'
            FROM hub_cluster_plan
            JOIN hub_cluster_plan_item
            ON hub_cluster_plan.id = hub_cluster_plan_item.cluster_plan_id
            JOIN shipping_shippingitem
            ON hub_cluster_plan_item.shipping_item_id = shipping_shippingitem.id
            JOIN location_sector
            ON shipping_shippingitem.designated_sector_id = location_sector.id
            JOIN location_address
            ON shipping_shippingitem.address_id = location_address.id
            WHERE (plan_date = '{plan_date}' AND plan_no = {plan_no})
        """
        return self.db_handler.fetch_data("daas", query)
