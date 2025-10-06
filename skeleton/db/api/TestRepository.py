from db.models import Test

class TestRepository:
    def __init__(self, ):
        pass

    def collect_test(self, test: Test):
        temp = {
            'id': test.pk,
            'name': test.name
        }
        return temp

    def getTest(self, id):
        test = Test.objects.get(pk = id)
        return self.collect_test(test)
    
    # Can update test, if "id" in test_data
    def postTest(self, test_data): 
        if 'id' in test_data:
            test = Test.objects.get(pk = test_data['id'])
        else:
            test = Test()

        test.name = test_data.get('name', '')
        test.save()
        return self.collect_test(test)
    
    def deleteTest(self, id):
        test = Test.objects.get(pk = id)
        test.delete()
        return id
