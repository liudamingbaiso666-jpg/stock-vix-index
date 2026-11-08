"""Offline regression checks for historical announcement-date collection."""
import importlib.util
import pathlib
import unittest

SCRIPT=pathlib.Path(__file__).with_name("collect_600900.py")
spec=importlib.util.spec_from_file_location("collect_600900",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeResponse:
    def __init__(self,payload):
        self.payload=payload
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


class FakeSession:
    def __init__(self,items):
        self.items=items
        self.params=[]
    def get(self,url,params,**kwargs):
        self.params.append(params)
        return FakeResponse({"data":{"list":self.items,"total_hits":len(self.items)}})


class AnnouncementTests(unittest.TestCase):
    def test_valid_date_and_report_are_preserved(self):
        session=FakeSession([{
            "title":"长江电力：2023年年度报告",
            "notice_date":"2024-04-30 00:00:00",
            "art_code":"AN202404300001"
        }])
        rows,error=mod.collect_eastmoney_disclosures(session)
        self.assertIsNone(error)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["published_date"],"2024-04-30")
        self.assertEqual(rows[0]["source"],"eastmoney_notice_index")
        self.assertEqual(session.params[0]["stock_list"],"600900")
        self.assertEqual(session.params[0]["client_source"],"web")

    def test_empty_response_explains_missing_dates(self):
        rows,error=mod.collect_eastmoney_disclosures(FakeSession([]))
        self.assertEqual(rows,[])
        self.assertIn("0 notice items",error)

    def test_non_report_notice_rejected(self):
        rows,error=mod.collect_eastmoney_disclosures(FakeSession([{
            "title":"长江电力：关于担保事项的公告",
            "notice_date":"2024-04-30","art_code":"AN1"
        }]))
        self.assertEqual(rows,[])
        self.assertIn("1 notice items",error)


if __name__=="__main__":
    unittest.main()
